"""
Mode 4 Prompt Agent — на основе фото личности и цитаты генерирует:
- video_prompt: кинематографичный промпт для генерации видео (в стиле Достоевского)
- voice_description: описание голоса (для справки)
- script_ru: цитата на русском (для субтитров)
- script_en: перевод цитаты на английский (если bilingual)
"""

from __future__ import annotations

import base64
import json
import random
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from utils.llm import make_llm

VISION_MODEL = settings.openrouter_vision_model

# Случайная «зерновая» подсказка типа локации на запрос: разнообразие между цитатами.
# Модель ОБЯЗАНА перенести тип сцены в эпоху, регион и биографию конкретного персонажа (не копировать буквально, если несовместимо).
_LOCATION_STEERING_HINTS: tuple[str, ...] = (
    "covered market or exchange arcade, stalls, fabrics, morning bustle",
    "stone quay, boats, rope, gulls, drizzle",
    "cathedral or temple aisle: pillars, stone floor, dim light",
    "rampart or fortress wall walk, crenellations, wind",
    "riverside willows, reed bank, small jetty, golden hour",
    "vineyard terrace, stone wall, vine rows",
    "palace or manor gallery: parquet, portraits, tall windows",
    "lecture hall or examination room: benches, chalkboard, inkstands",
    "apothecary or workshop: jars, herbs, single lamp",
    "scriptorium or archive: lecterns, books, narrow windows",
    "forge or armoury: anvil, coals, tools",
    "barn or threshing floor: straw, beams, dust in sunbeams",
    "orchard or garden wall, bloom, wooden fence",
    "mountain trail: wind, scree, distant peaks",
    "caravanserai courtyard: arcades, well, pack animals",
    "steppe camp: tents, fire smoke, wide sky",
    "irrigated fields or terraces, paths, workers",
    "quiet garden walk or shaded path at dusk: trees, lamplight or torches (interpret only with flora and architecture of the character's region)",
    "forum or agora edge: colonnade, merchants, bright noon",
    "Roman bath interior: marble, steam, oil lamps",
    "amphitheatre stone seats, sand, long shadows",
    "ship or boat deck: oars, spray, coastline",
    "counting-house above warehouse: ledgers, harbor noise",
    "coaching inn courtyard: carriage, lanterns, cobbles",
    "railway platform: iron canopy, steam (only if era allows)",
    "theatre backstage: ropes, costumes, footlights",
    "music room: harpsichord or piano, candles",
    "hospital or ward of the period: beds, screens",
    "law court antechamber: benches, clerks",
    "prison yard or corridor: grilles, worn stone",
    "captain's cabin: maps, compass, sea window",
    "observatory: brass instruments, charts, night sky",
    "library reading room: stacks, ladder, green lamps",
    "coffeehouse or club room: chairs, newspapers, foggy window",
    "artist's studio: easel, casts, north light",
    "greenhouse or orangery: glass, plants, winter sun",
    "stable aisle: straw, tack, horses",
    "mill interior: stones, grain dust, light shaft",
    "bridge midpoint: arches below, wind",
    "city gate or toll: carts, guards, dust",
    "monastery cloister: garth, fountain, arcades",
    "courtyard of worship: tiles, fountain, quiet hour",
    "roadside shrine: candles, steps, trees",
    "fishing village: nets, racks, low sun",
    "salt works or drying yard: white glare, workers",
    "quarry or stone yard: blocks, chisels, dust",
    "fair or feast-day square: booths, banners",
    "cemetery gate: iron, yew, overcast",
    "roof or belvedere: chimneys, pigeons, sunset",
    "wine cellar: brick vault, racks, candle",
    "war tent or field HQ: maps, pennants, twilight",
    "siege camp: earthworks, smoke, dawn",
    "hunting lodge hall: fire, trophies, shadows",
    "scholar's room: low desk, brush and ink, garden glimpse",
    "carriage interior: rain on window, lamp sway",
    "lighthouse gallery: lantern glass, sea spray",
    "early factory floor: belts, high windows (only if era fits)",
    "dockside tavern back room: barrels, harbor light",
    "formal garden: hedges, gravel, fountain",
    "moor or heath: bent grass, stone, lowering sky",
    "oasis fringe: palms, pool, heat shimmer",
    "frozen river or winter fair (only if era and climate fit)",
)


def _pick_location_steering_hint() -> str:
    return random.choice(_LOCATION_STEERING_HINTS)


def _speech_language_user_hint(
    quote: str,
    *,
    bilingual: bool,
    source_russian_only: bool,
    auto_detect_lang: bool,
    subtitle_lang: str,
) -> str:
    """Одна строка в user-message: жёстко задаёт speaking in X под язык цитаты."""
    if bilingual and source_russian_only:
        return (
            "ЯЗЫК РЕЧИ (bilingual): в video_prompt_ru — speaking in Russian и только русская цитата; "
            "в video_prompt_en — speaking in English и только английский перевод; без Latin, без двух цитат в одном промпте.\n\n"
        )
    if auto_detect_lang:
        return (
            "ЯЗЫК РЕЧИ: определи detected_lang; в video_prompt speaking in [Language] совпадает с языком цитаты "
            "(ru→Russian, en→English, de→German, fr→French, …); цитата в кавычках на том же языке.\n\n"
        )
    if re.search(r"[\u0400-\u04FF]", quote):
        lang = "Russian"
    elif subtitle_lang.lower() == "en":
        lang = "English"
    else:
        lang = "Russian"
    return (
        f"ЯЗЫК РЕЧИ: в video_prompt — speaking in {lang}; цитата в кавычках строго на этом языке; "
        f"не Latin/Greek, если цитата не на латыни/греческом дословно.\n\n"
    )


_SYSTEM = """Ты — эксперт по кинематографичной AI-генерации и исторической достоверности.

По фото личности, её имени и цитате создаёшь ДЕТАЛЬНЫЙ промпт для video-to-video генерации (Veo, Runway, fast-gen.ai).

## ПОРЯДОК РАБОТЫ (обязательно — не переставляй)
1. **Сначала** зафиксируй **требования к итоговому ролику** под генератор (fast-gen.ai, референс лица, вертикальный клип): формат **9:16 portrait**, **photorealistic**, один непрерывный кадр с **одним** говорящим персонажем по фото-референсу, **озвучка** = дословная **одна** цитата в кавычках на языке ролика (RU/EN), **костюм и локация в точности под идентифицированного человека и его эпоху/регион**, **максимально кинематографичная** постановка (свет, глубина, кадр, атмосфера), без пустого фона. Сцена должна иметь **сильный визуальный хук уже в первые мгновения**: выразительный foreground, объёмный свет, погода/атмосфера, узнаваемую архитектурную или природную доминанту. **КРИТИЧНО: в самом сгенерированном кадре не должно быть НИКАКОГО текста** — no subtitles, no captions, no title cards, no lower-thirds, no burned-in quote text, no readable signs, no letters, no logos, no watermark.
2. **Обязательно проанализируй текст цитаты** (смысл, тон, настроение, напряжение, ирония, торжественность, меланхолия, надежда, бунт, тишина размышления и т.д.) и **видимые образы**, которые она вызывает. Этот анализ **не выводи отдельным полем** — но **вся** сцена (выбор варианта локации в рамках типа из LOCATION_STEERING, время суток, погода за окном, плотность тумана/пыли, контраст света, цветовой ключ, микродвижения, выражение лица до и во время речи) должна **подчиняться настроению и смыслу цитаты**, не противореча эпохе и личности.
3. **Затем** **на основе требований + анализа цитаты** целиком сформулируй **video_prompt** (английский, **70–110 слов** по структуре ниже — плотно, без воды). Сцена должна быть **визуально цепляющей**, но правдоподобной: не просто «исторический интерьер», а **одна запоминающаяся среда с 3–5 фиксированными опорными деталями**, которые можно удержать между фрагментами одной и той же цитаты. В режиме **bilingual**: **сначала полностью** `video_prompt_ru`, **потом** `video_prompt_en` (тот же человек и та же сцена — только перевод описания + другой язык речи и цитаты в кавычках). Поле `video_prompt` = копия английской версии (как в инструкции ниже).
4. **После** готовых промптов для видео заполни `script_ru`, `script_en`, `person_name_en` (если нужно), `voice_description` — строго **согласованно** с сценой и **настроением цитаты** (цитата в промпте и в script_* совпадают по смыслу и языку).

## ИСТОРИЧЕСКАЯ ТОЧНОСТЬ И ФАКТЫ (критично):
- По **имени** (и цитате, если даёт подсказку) определи: **век или узкий диапазон лет**, **регион/государство**, **социальный статус и род занятий** (сенатор, монах, офицер, купец, учёный…). Опирайся на общеизвестные исторические сведения о таких людях и их эпохе; не выдумывай несуществующие титулы, формы одежды или технологии.
- **Одежда и локация — в точности под этого человека и эту эпоху**, не «в духе эпохи» и не декоративный исторический костюм: каждый предмет гардероба и каждый элемент фона должен быть **оправдан** сочетанием *конкретная личность (роль, сан, климат жизни)* + *узкий исторический слой* + *регион*. Запрещены универсальные шаблоны («средневековье», «викторианский кабинет», «античность») без привязки к **этому** имени и **этому** веку.
- Одежда и локация должны быть **согласованы** друг с другом и с эпохой: нельзя смешивать века, нельзя ставить персонажа в интерьер с предметами, появившимися позже (электричество до эпохи, огнестрел до изобретения, стёкла панорамные в античности и т.д.).
- Освещение и быт: только то, что **реально могло быть** (свеча, лучина, масляный светильник, газовый фонарь улицы, дневной свет через конкретный тип окон — в зависимости от периода).
- Если личность **малоизвестна** — не придумывай экзотику: возьми **характерный, хорошо документированный** архетип среды для данного статуса и региона (ткани, крой мебели, тип здания того времени).
- В english video_prompt избегай размытых формулировок вроде «period costume», «old room»: всегда **конкретные** термины (названия предметов одежды, детали архитектуры, материалы).
- **Реквизит и техника в кадре** — только то, что могло существовать в выбранном веке и регионе. Примеры ошибок: магнитный компас-коробка и «современная» навигация в раннем Риме; электрический свет до эпохи; панорамное остекление там, где его не было. Навигация античности — ориентиры по берегу, звёзды, гардемарины, восковые таблички, свитки-маршруты; не выдумывай приборы из более поздних веков.
- **LOCATION_STEERING и чужая культура**: текст подсказки типа локации может звучать «нейтрально» или с чужим примером — ты всё равно **не копируешь** растения, архитектуру, тип светильников и декор **другой цивилизации**, чем у персонажа. Примеры: для **римского или эллинистического** мыслителя (Сенека, Марк Аврелий, Платон…) **запрещены** бамбук, пагоды, бумажные фонари в азиатском стиле, чайный павильон в духе Восточной Азии — вместо «садовой дорожки / сумерек» дай **римскую виллу, перистиль, средиземноморские деревья, мрамор, масляный светильник**. Для персонажа из Китая/Японии/Персии — наоборот, не подставляй римский форум. Смысл подсказки = **тип пространства** (аллея, двор, зал), а **визуальный словарь** только из эпохи и **географии этого человека**.

## ЯЗЫК РЕЧИ В video_prompt (обязательно)
- Фраза **speaking in [Language]** должна **совпадать с языком цитаты в кавычках** в том же промпте: русская цитата → `speaking in Russian`; английская → `speaking in English`; и т.д. по `detected_lang` при auto_detect.
- **Запрещено**: писать Latin, Ancient Greek и т.п. для озвучки, если в кавычках **не** дословный текст на этом языке (цитата для пользователя на русском/английском — персонаж «говорит» на языке этой цитаты в промпте, это художественный приём для зрителя).
- **Один** пункт РЕЧЬ — **одна** цитата **одним** языком; не дублировать в одном video_prompt две реплики на разных языках (не «saying: RU…» и отдельно «He speaks EN…»).
- Режим **bilingual**: в `video_prompt_ru` — только `speaking in Russian` и русская цитата; в `video_prompt_en` — только `speaking in English` и английский перевод; поле `video_prompt` = как согласовано в инструкции ниже.
- **ТЕКСТ В КАДРЕ ЗАПРЕЩЁН**: даже если цитата произносится голосом, она НЕ должна быть напечатана внутри видео. Запрещены subtitles, captions, quote text, title overlays, lower-thirds, logos, watermark, any readable letters or words anywhere in frame.

## ОДЕЖДА — точное соответствие **человеку** и **эпохе** (блок ПЕРСОНАЖ, на английском; критично):
- Сначала мысленно зафиксируй: **век/десятилетие**, **регион**, **пол и возраст по фото**, **род занятий и статус** по имени и общеизвестным фактам. Вся одежда должна быть **проверяема** для этой комбинации (не «костюм эпохи» вообще, а одежда **этого** человека или **такого** статуса в **этом** месте и времени).
- **Соответствие фото**: силуэт и тип наряда в промпте (гражданский / военный / духовный / придворный и т.д.) должен **совпадать** с тем, что читается с референса; нельзя превращать человека в «другую роль» или другой чин. Детали (ткань, фурнитура, головной убор) — **эпохальная доводка** того же типа образа, а не подмена профессии или статуса.
- Для широко известных личностей — опирайся на **характерные** для них типы одежды того периода (военная форма века, сана, придворный/гражданский костюм, монашеское облачение, мундир, халат учёного и т.д.), не выдумывай фантастические варианты.
- **Минимум 4–6 конкретных пунктов** в video_prompt про одежду и убор: ткани с названием фактуры, цветовые акценты, крой, длина, ворот, рукава, головной убор или причёска эпохи, обувь, перчатки/без, украшения или регалии **только** если уместны.
- **Ткани и фактура**: шерсть, лён, сукно, шёлк, кожа, мех, бархат, камлот — по статусу, климату региона и веку; плотность (heavy wool greatcoat, fine cambric shirt).
- **Крой и силуэт** строго века: не подмешивай силуэт XX–XXI века.
- **Застёжки и узлы**: пуговицы, крючки, шнуровка, пояс, фибула — только периода.
- Если на фото видна одежда — **не противоречь** ей по типу одежды (верх/длина/головной убор), но **детализируй и эпохализируй** под выведенный исторический контекст (как та же роль выглядела бы в документальной реконструкции).
- Запрещено: анахронизмы, обобщения «period costume», «vintage suit» без конкретики, смешение национальных форм без оснований.

## АНАЛИЗ ЦИТАТЫ → НАСТРОЕНИЕ И ФОН (обязательно; делает только ты, LLM)
- **Прочитай цитату целиком**: что чувствует говорящий, какой ритм фразы, есть ли контраст, отчаяние, ирония, пророчество, интимность, публичный вызов, тихая исповедь.
- **Переведи это в визуальную и световую подачу** в рамках исторической правды: например торжественная цитата — более сдержанный контраст, высокий ключ или монументальный свет; мрачная — chiaroscuro, узкий луч, дождь за окном **если** век и регион позволяют; интимная — тёплый близкий свет, сужение глубины; бунтарская — резче контур, ветер/движение ткани в кадре **без** анахронизма.
- **Фон и реквизит** в выбранном месте должны **усиливать настроение цитаты** (пустой зал vs тесная комната, открытый горизонт vs решётка окна, порядок vs накопившийся беспорядок — только если это правдоподобно для эпохи и LOCATION_STEERING). Не ставь нейтральный «красивый интерьер», если цитата кричит о другом эмоциональном регистре.
- Обязательно придумай **одну визуальную доминанту**, которая делает кадр цепляющим без дешёвого кликбейта: окно с бурей и рваным светом, длинная галерея с глубиной арок, мокрая набережная с бликами, огонь очага/лампы на фактурной стене, резкий силуэт на фоне рассвета, тесный кабинет с нависающими полками и т.п. Эта доминанта должна подходить и **человеку**, и **смыслу цитаты**.

## КИНЕМАТОГРАФИЧНЫЙ ФОН, ПРИВЯЗАННЫЙ К **ЛИЧНОСТИ**, **ЭПОХЕ** И **НАСТРОЕНИЮ ЦИТАТЫ** (обязательно для всего video_prompt)
- Сначала **зафиксируй якорь одной фразой** (на английском в блоке ОКРУЖЕНИЕ): **век + регион + тип места, где такой человек реально мог бы оказаться** — например: *late 19th-century Russian provincial study*, *High Roman Empire interior*, *English Regency drawing room*. Это не декорация: локация должна **логично следовать** из статуса, региона жизни и периода **этой** личности (при известной биографии — ориентир на характерные для неё обстановки; при малой известности — **документируемый** архетип места для **того же** статуса и региона), и **дополнительно** быть выбрана/детализирована так, чтобы **настроение цитаты** читалось в пространстве и свете.
- Фон — не «иллюстрация», а **кадр из исторической драмы**: глубина (передний план / середина / даль), мотивированный свет (от окна, свечей, очага, уличных фонарей — что уместно веку), объём воздуха, пыль/туман/пар при необходимости, **цветовая гамма** согласована и с эпохой, и с **эмоциональным тоном цитаты** (тепло/холод, насыщенность, золото сумерек vs стальной рассвет — по смыслу реплики).
- Если эта сцена потом будет разбита на несколько клипов, она должна быть **легко удерживаемой как один locked set**: те же архитектурные оси, та же доминанта, те же крупные объекты, тот же источник света и направление взгляда пространства.
- Архитектура, мебель, бытовые предметы, окна, уличная застройка за окном — **только** из выбранного века **и** региона персонажа; без смешения стилей и без «универсальной старины». Каждая видимая деталь фона должна **переноситься** в узкий слой времени **этого** человека.
- В english video_prompt используй **максимально кинематографичный** киноязык: lensing (например shallow depth, medium portrait framing), layered depth, leading lines, **chiaroscuro** или soft wrap light по настроению цитаты, atmospheric haze, **motivated** practicals в кадре, subtle camera-facing blocking — но **без** названий фильмов и режиссёров.

## ОКРУЖЕНИЕ — **видимый** фон с глубиной (никогда void, пустая студия, однотонный экран).

Пометь тип: *documented setting* (B) или *portrait-with-environment* (A).

### B) Осмысленное место (**по умолчанию** — главный способ дать кинематографичный эпохальный фон)
- В **каждом** запросе пользователь даёт строку **LOCATION_STEERING_FOR_THIS_REQUEST** — это **случайный тип локации для разнообразия** между разными цитатами. Твоя задача: воплотить **тот же тип сцены** (рынок / набережная / библиотека / поле / казарма / мастерская и т.п.) в **конкретном месте и архитектуре эпохи и региона персонажа** — чтобы зритель **узнал** и эпоху, и географию, и социальный слой **этого** человека, а не абстрактную «старину». Среди допустимых вариантов этого типа выбирай **тот подтип локации и ту атмосферу** (плотность людей, шум, одиночество, величие, уют, угроза), который **лучше всего резонирует с настроением цитаты**.
- Если буквальная подсказка **географически или хронологически невозможна** (например, римский форум у северного мореплавателя XVII в.) — **не игнорируй** подсказку: замени на **эквивалент того же типа** в правильном веке и регионе (например, торговая площадь / пристань своего времени). **Никогда** не переноси в кадр детали из подсказки, которые принадлежат **другой** культуре, чем персонаж (см. правило про LOCATION_STEERING и чужую культуру выше).
- Интерьер или натура **строго той же эпохи и того же региона**, что персонаж; дополнительно согласуй с биографией, статусом и образами цитаты, если они требуют другого, **но всё равно сохрани «тип» из подсказки**, когда это совместимо. **Итоговая локация обязана быть согласована с личностью**: не ставь купца в казарму, монаха в придворный бал без основания в цитате/биографии.
- **Минимум 4–5 видимых деталей** + **2 кинематографических** (ключ, тени, планы, перспектива).
- Запрещено: игнорировать LOCATION_STEERING без причины; ставить «любимый» один и тот же кабинет вопреки подсказке; случайные декорации вне эпохи и личности.

### A) Портрет с глубиной (**редко**, очень абстрактная цитата)
- Фон **всё равно эпохальный**: размытый, но узнаваемый интерьер или вид из окна **того же века** — силуэты мебели эпохи, рама окна, колонна, шторы, полки, штукатурка.
- **Запрещено**: flat backdrop, пустая студия, градиент без предметов.
- **4–5 деталей** фона + указание, как свет из эпохи (свеча, окно) создаёт объём.

### Общее
- Не смешивай A и B. **Если сомневаешься — B** с типичной для личности обстановкой **конкретного века**.
- Shallow DOF допустим: фон мягкий, но **эпоха и пространство читаются** по силуэтам и свету.

## ДЕТАЛЬНОСТЬ video_prompt (70–110 слов, плотно по фактам):
Пиши на английском. **Каждый абзац структуры — с кинематографической плотностью** (конкретные планы, свет, текстура воздуха), не сухой список. Структура:

1. ПЕРСОНАЖ (подробно): внешность по фото, возраст, волосы/борода; **одежда — минимум 4–6 конкретных деталей**, каждая **в точности** для **этого** человека (имя+фото+статус) и **этой** эпохи/региона (см. «ОДЕЖДА»); поза, осанка; **микровыражение и взгляд**, согласованные с **настроением цитаты** до начала речи.
2. ОКРУЖЕНИЕ (подробно): якорь — век + регион + тип места на английском, **где такой человек уместен**; **обязательно** опирайся на **LOCATION_STEERING_FOR_THIS_REQUEST** (тип сцены), перенесённый в **исторически и социально достоверную** локацию для **этой** личности, с **эмоциональной окраской под цитату** (не нейтральный фон). Затем **B** или **A**; **минимум 4–5 видимых деталей фона** + **кинопостановка** (глубина, направление взгляда в пространство). Среди этих деталей выдели **3–5 fixed anchor details**, которые потом можно удерживать одинаковыми между всеми фрагментами.
3. ОСВЕЩЕНИЕ И АТМОСФЕРА: **максимально кинематографично**, мотивированно эпохой **и настроением цитаты** — ключ, контраст, цвет, источники света того времени, тени, воздух (пыль, туман, дождь за стеклом — если уместно веку и тону реплики).
4. ДВИЖЕНИЕ: медленный, выразительный blocking (шаг, поворот, остановка, лицом к камере) — **ритм под смысл** цитаты, не шаблон «walks slowly» одной строкой без контекста. Начало клипа должно давать **instant visual read**: силуэт, движение света, жест, поворот головы, вход в луч света, шаг из тени в объём.
5. РЕЧЬ: He/She begins speaking in **[exactly the language of the quoted text]**, his/her voice [тембр **в духе настроения цитаты**], saying: "[одна цитата — тот же язык]". Expression: [как меняется лицо — **в связке с тоном цитаты**]. Без Latin/другого языка при цитате на RU/EN.
6. Технические: period-accurate **high-end cinematic** framing, photorealistic, 8K, vertical 9:16 portrait; shallow DOF только если эпохальный фон **читается** по свету и силуэтам. Add explicit clean-frame rule: no on-screen text, no subtitles, no captions, no logos, no watermark, no readable signage.

Имя в промпте НЕ писать. Описывать по роли и внешности, с **конкретной** эпохальной одеждой и местом (без штампов и без имени).

**КРИТИЧНО ДЛЯ СИНТАКСИСА:** ответ — **один завершённый JSON-объект**: закрой все строки кавычками и объект фигурной скобкой `}`. Если объём ответа ограничен — **сократи video_prompt**, но **никогда** не обрывай JSON посередине поля.

Верни ТОЛЬКО JSON. **Заполняй ключи в этом порядке** (сначала всё для видео-промпта, потом сценарий и голос):
{
  "video_prompt": "70–110 слов на английском: после анализа настроения цитаты; одежда под эпоху; фон и свет под цитату и личность; максимально кинематографично",
  "video_prompt_ru": "только если bilingual — с 'speaking in Russian'; пишется СРАЗУ после требований, до EN-версии",
  "video_prompt_en": "только если bilingual — с 'speaking in English'; та же сцена, что в RU",
  "voice_description": "после промптов: тембр и подача под настроение цитаты и сцену",
  "script_ru": "цитата дословно",
  "script_en": "перевод (если bilingual ИЛИ subtitle_lang=en)",
  "person_name_en": "имя автора на английском (только если source_russian_only+bilingual)",
  "detected_lang": "ru|en|de|fr|es|... (если auto_detect — ISO 639-1 код языка цитаты)"
}
При auto_detect: определи язык цитаты, верни detected_lang. Субтитры = цитата как есть. script_ru/script_en — устаревшие при auto_detect.

Режим source_russian_only + bilingual: цитата и имя автора ВВОДА на русском. Обязательно:
- script_ru — цитата дословно по-русски;
- script_en — точный литературный перевод цитаты на английский;
- person_name_en — принятое английское написание имени (Marcus Aurelius, Leo Tolstoy, …);
- video_prompt_ru — персонаж/сцена, в речи дословная русская цитата в кавычках;
- video_prompt_en — НЕ переписывай заново внешность: это ТОТ ЖЕ человек и ТА ЖЕ сцена, что в video_prompt_ru. Скопируй блоки 1–4 (персонаж, окружение, свет, движение) с video_prompt_ru, переведи их на английский ДОСЛОВНО по смыслу, без новых черт лица/причёски/возраста; **настроение цитаты и кинематографика** те же. Меняется только пункт РЕЧЬ: speaking in English + английская цитата в кавычках. Лицо и тело задаёт только фото-референс в генераторе — в тексте не противоречь фото и не описывай «другого» человека.
- video_prompt — ВСЕГДА заполни: дублируй video_prompt_en (или общий промпт на английском 70–110 слов). Без ключа video_prompt ответ считается ошибочным."""


def _image_to_base64_url(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    data = p.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")
    ext = p.suffix.lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{b64}"


async def _parse_json_response(text: str, llm) -> dict:
    from utils.json_parse import parse_json_safe

    try:
        return parse_json_safe(text)
    except Exception as exc:
        logger.warning(
            "[Mode4 Prompt] JSON parse failed, trying repair. "
            f"Raw length={len(text)}, first 500 chars={text[:500]!r}, error={exc}"
        )

    salvaged = _salvage_partial_prompt_json(text)
    if salvaged:
        logger.warning("[Mode4 Prompt] Salvaged partial JSON from raw response")
        return salvaged

    repair_system = (
        "You are a JSON repair assistant. "
        "Return ONLY one valid JSON object. No markdown, no code fences, no commentary. "
        "Use exactly these keys: "
        "video_prompt, video_prompt_ru, video_prompt_en, voice_description, "
        "script_ru, script_en, person_name_en, detected_lang. "
        "If a value is missing, use an empty string. "
        "If video_prompt was cut off mid-string, rewrite it as a **complete** English prompt, "
        "70-110 words max, same scene intent, then close the JSON properly."
    )
    repair_human = (
        "Repair this malformed response into valid JSON only.\n\n"
        f"{text[:12000]}"
    )
    # Ремонт — только текст; отдельная модель с большим лимитом вывода (vision-ответ часто обрезается).
    repair_llm = make_llm(temperature=0.1, max_tokens=8192)
    repair_resp = await repair_llm.ainvoke(
        [SystemMessage(content=repair_system), HumanMessage(content=repair_human)]
    )
    repaired_text = (
        repair_resp.content if hasattr(repair_resp, "content") else str(repair_resp)
    )

    try:
        data = parse_json_safe(repaired_text)
        logger.warning("[Mode4 Prompt] JSON repair succeeded")
        return data
    except Exception as exc:
        salvaged = _salvage_partial_prompt_json(repaired_text)
        if salvaged:
            logger.warning("[Mode4 Prompt] Salvaged partial JSON from repaired response")
            return salvaged
        logger.error(
            "[Mode4 Prompt] JSON repair failed. "
            f"Repaired length={len(repaired_text)}, first 500 chars={repaired_text[:500]!r}, error={exc}"
        )
        raise


def _strip_code_fences_loose(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        first_nl = raw.find("\n")
        if first_nl != -1:
            raw = raw[first_nl + 1 :].strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
        elif "```" in raw:
            raw = raw.split("```", 1)[0].strip()
    return raw


def _clean_json_string_fragment(s: str) -> str:
    out = (s or "").strip()
    out = out.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
    out = out.replace('\\"', '"')
    out = out.replace("\\/", "/")
    out = re.sub(r"\s+", " ", out).strip(" \n\r\t,}")
    return out


def _salvage_partial_prompt_json(text: str) -> dict | None:
    """
    Если LLM оборвал JSON посередине строки, попробуем вытащить хотя бы video_prompt
    и любые уже начатые поля, чтобы пайплайн не падал.
    """
    raw = _strip_code_fences_loose(text)
    if not raw or "video_prompt" not in raw:
        return None

    key_pattern = re.compile(
        r'"(video_prompt|video_prompt_ru|video_prompt_en|voice_description|script_ru|script_en|person_name_en|detected_lang)"\s*:\s*"',
        flags=re.DOTALL,
    )
    matches = list(key_pattern.finditer(raw))
    if not matches:
        return None

    data: dict[str, str] = {}
    for i, m in enumerate(matches):
        key = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        chunk = raw[start:end]
        if i + 1 < len(matches):
            chunk = re.sub(r'"\s*,?\s*$', "", chunk, flags=re.DOTALL)
        value = _clean_json_string_fragment(chunk)
        if value:
            data[key] = value

    if not any((data.get("video_prompt"), data.get("video_prompt_ru"), data.get("video_prompt_en"))):
        return None

    for key in (
        "video_prompt",
        "video_prompt_ru",
        "video_prompt_en",
        "voice_description",
        "script_ru",
        "script_en",
        "person_name_en",
        "detected_lang",
    ):
        data.setdefault(key, "")
    return data


def _ensure_video_prompt(data: dict) -> None:
    """
    LLM иногда отдаёт только video_prompt_ru / video_prompt_en (bilingual), без video_prompt.
    """
    vp = (data.get("video_prompt") or "").strip()
    if vp:
        return
    ru = (data.get("video_prompt_ru") or "").strip()
    en = (data.get("video_prompt_en") or "").strip()
    if en:
        data["video_prompt"] = en
        logger.warning("[Mode4 Prompt] Filled video_prompt from video_prompt_en")
    elif ru:
        data["video_prompt"] = ru
        logger.warning("[Mode4 Prompt] Filled video_prompt from video_prompt_ru")
    else:
        raise ValueError(
            "Prompt agent missing video_prompt (and no video_prompt_ru / video_prompt_en)"
        )


async def run_quote_prompt_agent(
    photo_path: str | Path,
    quote: str,
    person_name: str = "",
    bilingual: bool = False,
    subtitle_lang: str = "ru",
    auto_detect_lang: bool = False,
    source_russian_only: bool = False,
    location_steering_hint: str | None = None,
) -> dict:
    """
    Анализирует фото личности и цитату, возвращает промпты для видео.

    Args:
        photo_path: путь к фото личности
        quote: цитата (на любом языке при auto_detect_lang)
        person_name: имя личности (для контекста, в промпт не включать!)
        bilingual: если True — 2 фрагмента (RU + EN)
        subtitle_lang: "ru" | "en" — язык субтитров при одном фрагменте
        auto_detect_lang: если True — определить язык цитаты, субтитры = цитата как есть
        source_russian_only: цитата и имя на русском; при bilingual — перевод для EN-версии и person_name_en

    Returns:
        {
            "video_prompt": str,
            "voice_description": str,
            "script_ru": str,
            "script_en": str,
            "detected_lang": str  # при auto_detect_lang: ru, en, de, fr и т.д.
        }
    """
    img_url = _image_to_base64_url(photo_path)
    # Компактный video_prompt (70–110 слов) + max_tokens снижают обрыв JSON у провайдера.
    llm = make_llm(temperature=0.3, model=VISION_MODEL, max_tokens=8192)

    auto_hint = (
        "\n\nauto_detect_lang: True — ОПРЕДЕЛИ язык цитаты (ru, en, de, fr, es, it, pl, ...). "
        "Верни detected_lang. video_prompt: укажи 'speaking in [Language]' по определённому языку. "
        "Субтитры = цитата без изменений."
    ) if auto_detect_lang else ""

    ru_bilingual_hint = (
        "\n\nsource_russian_only: True — цитата и имя автора УЖЕ на русском. "
        "Сгенерируй ДВЕ версии промптов (video_prompt_ru + video_prompt_en), script_ru, script_en, person_name_en. "
        "ОБЯЗАТЕЛЬНО также ключ video_prompt — скопируй туда video_prompt_en (полный английский промпт). "
        "Имя автора в промпты НЕ включать; для подписи пользователю нужен person_name_en. "
        "КРИТИЧНО: сначала полностью сформируй video_prompt_ru (одно лицо/сцена по фото). "
        "video_prompt_en = тот же персонаж и сцена (перевод описания), отличается только язык речи и цитата в кавычках. "
        "Запрещено в EN-версии выдумывать другую внешность."
    ) if source_russian_only and bilingual else ""

    location_steering = " ".join((location_steering_hint or "").split()).strip() or _pick_location_steering_hint()
    speech_hint = _speech_language_user_hint(
        quote,
        bilingual=bilingual,
        source_russian_only=source_russian_only,
        auto_detect_lang=auto_detect_lang,
        subtitle_lang=subtitle_lang,
    )

    msg = HumanMessage(content=[
        {"type": "text", "text": (
            "ШАГ 1 — Требования к видео (держи в голове до конца): клип для fast-gen.ai с референсом лица; вертикаль 9:16; "
            "фотореализм; один говорящий персонаж; в промпте — **максимально кинематографичная** сцена + в кавычках **ровно** та цитата, что задаёт пользователь, на языке озвучки.\n"
            "ОЧЕНЬ ВАЖНО: в финальном сгенерированном изображении/видео не должно быть никакого напечатанного текста: "
            "no subtitles, no captions, no quote text on screen, no title cards, no lower-thirds, no logos, no watermark, no readable signs.\n"
            "Сделай кадр визуально цепляющим уже в первые секунды: нужен один сильный исторически правдоподобный visual hook, а не просто нейтральный красивый фон.\n"
            "ШАГ 1b — **Проанализируй цитату** (тон, настроение, смысл, образы) и подстрой **фон, свет, атмосферу, выражение, голос** под это; эпоха и личность остаются жёсткими рамками.\n"
            "ШАГ 2 — Составь **сначала** полные video_prompt / video_prompt_ru+en (как в system), **потом** script_*, voice_description и остальное.\n\n"
            + speech_hint
            + "ОДЕЖДА И ЛОКАЦИЯ: **в точности** под **этого** человека (имя + фото + реальный статус/роль) и **узкую** эпоху с **его** регионом; "
            "тип наряда с фото не подменяй другой ролью. Фон — то же: конкретное место и предметы **только** из века и места жизни такой личности, без «универсальной старины»; **настроение и детали фона** должны **резонировать с цитатой** (сам проанализируй текст). "
            "Минимум **4–6** конкретных элементов одежды в блоке ПЕРСОНАЖ на английском; без анахронизмов и без «period dress» без конкретики.\n\n"
            "LOCATION_STEERING_FOR_THIS_REQUEST (случайный тип локации для разнообразия между цитатами; **не копируй буквально**, если не сочетается с веком/регионом):\n"
            f"{location_steering}\n\n"
            "Обязательно: воплоти **этот тип места** в **исторически достоверной** локации для данной личности (архитектура, быт, география). "
            "При несовместимости — тот же **тип** сцены в правильной эпохе и месте. Фон кинематографичный, с глубиной; без void. "
            "Зафиксируй 3–5 якорных деталей сцены, чтобы её можно было удержать одинаковой между несколькими фрагментами. "
            "**B** по умолчанию; **A** — редко при очень абстрактной цитате (эпохальный размытый интерьер).\n\n"
            + (
                f"Имя личности (НЕ писать в промпте! Для эпохи, региона, одежды и локации): {person_name}\n\n"
                if (person_name or "").strip()
                else "Имя личности пользователь НЕ указал — определи эпоху, регион, одежду и локацию только по фото "
                "и по смыслу цитаты (исторический контекст реплики).\n\n"
            )
            + f"Цитата (вставить в video_prompt в кавычках): {quote}\n\n"
            + f"bilingual: {bilingual}\n"
            + f"subtitle_lang: {subtitle_lang}\n"
            + f"auto_detect_lang: {auto_detect_lang}\n"
            + f"source_russian_only: {source_russian_only}\n"
            + "video_prompt: 70–110 слов на английском (плотно). В явном виде свяжи окружение с подсказкой типа локации выше (перенос в эпоху персонажа) и с **настроением цитаты**; свет и кадр — **кинематографично**, не плоский репортажный кадр. "
            + "Обязательно опиши один сильный visual hook и 3–5 fixed anchor details сцены. "
            + "**Обязательно заверши весь JSON** (закрытые кавычки и `}`); если длинно — укороти описание, не обрывай посередине. "
            "Проверь: одежда ↔ личность ↔ эпоха; фон ↔ история ↔ **тон цитаты**; нет пустого фона. "
            "Цитату в кавычках. Отдельно и явно пропиши clean frame rule: no on-screen text, no subtitles, no captions, no logos, no watermark."
            + auto_hint
            + ru_bilingual_hint
            + " Верни ТОЛЬКО JSON."
        )},
        {"type": "image_url", "image_url": {"url": img_url}},
    ])

    resp = await llm.ainvoke([SystemMessage(content=_SYSTEM), msg])
    text = resp.content if hasattr(resp, "content") else str(resp)
    data = await _parse_json_response(text, llm)

    _ensure_video_prompt(data)

    data.setdefault("script_ru", quote)
    data.setdefault("script_en", "")
    data.setdefault("person_name_en", "")
    data.setdefault("voice_description", "")
    data.setdefault("detected_lang", "")

    if source_russian_only and bilingual:
        if not data.get("script_ru"):
            data["script_ru"] = quote
        if not (data.get("script_en") or "").strip():
            logger.warning("[Mode4 Prompt] Missing script_en — using Russian quote as fallback")
            data["script_en"] = quote
        if not (data.get("person_name_en") or "").strip():
            logger.warning("[Mode4 Prompt] Missing person_name_en — using Russian name as fallback")
            data["person_name_en"] = person_name

    if auto_detect_lang:
        # Субтитры = цитата как есть (в языке ввода)
        det = (data.get("detected_lang") or "en").strip().lower()[:2]
        if det == "ru":
            data["script_ru"], data["script_en"] = quote, ""
            data["detected_lang"] = "ru"
        else:
            # en, de, fr, es, it... — используем script_en
            data["script_ru"], data["script_en"] = "", quote
            data["detected_lang"] = "en"
    else:
        if not data.get("script_ru"):
            data["script_ru"] = quote
        if not data.get("script_en") and bilingual:
            data["script_en"] = quote  # fallback if no translation
        elif subtitle_lang == "en" and not data.get("script_en"):
            data["script_en"] = data.get("script_ru", quote)

    if bilingual:
        if not data.get("video_prompt_ru") and data.get("video_prompt"):
            data["video_prompt_ru"] = data["video_prompt"].replace("English", "Russian")
        if not data.get("video_prompt_en") and data.get("video_prompt"):
            data["video_prompt_en"] = data["video_prompt"].replace("Russian", "English")

    logger.success(f"[Mode4 Prompt] Generated video prompt for quote ({len(quote)} chars)")
    return data
