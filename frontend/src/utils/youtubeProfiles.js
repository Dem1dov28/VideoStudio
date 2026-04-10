/**
 * Слоты YouTube из GET /api/youtube/status: profile_list (новый формат) или profiles + profile_order.
 */
export function youtubeSlotsFromStatus(ytStatus) {
  if (!ytStatus) return [];
  const list = ytStatus.profile_list;
  if (Array.isArray(list) && list.length) return list;
  const profs = ytStatus.profiles || {};
  const order =
    Array.isArray(ytStatus.profile_order) && ytStatus.profile_order.length
      ? ytStatus.profile_order
      : Object.keys(profs);
  return order.map((id) => ({
    id,
    ...(profs[id] || {}),
    label: (profs[id] && profs[id].label) || id,
  }));
}
