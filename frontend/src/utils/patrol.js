/** 巡查路线比对的前端镜像逻辑：用于表单内实时预览，最终结果以后端计算为准。 */

export const DEVIATION_LEVELS = ['无偏离', '轻微偏离', '明显偏离'];

export const DEVIATION_TONES = {
  无偏离: 'tag-success',
  轻微偏离: 'tag-warning',
  明显偏离: 'tag-danger',
};

export const ARRIVAL_RATE_SIGNIFICANT_THRESHOLD = 70;
export const MISSED_SIGNIFICANT_THRESHOLD = 2;

export function deviationTone(level) {
  return DEVIATION_TONES[level] || 'tag-neutral';
}

/**
 * 比对计划点位与实际轨迹，返回 { arrivalRate, missed, extra, outOfOrder, level }。
 * plannedIds / actualIds 均为按顺序排列的公厕 ID 数组。
 */
export function compareRoute(plannedIds, actualIds) {
  const plannedSet = new Set(plannedIds);
  const actualSet = new Set(actualIds);
  const missed = plannedIds.filter((id) => !actualSet.has(id));
  const extra = actualIds.filter((id) => !plannedSet.has(id));
  const plannedSequence = plannedIds.filter((id) => actualSet.has(id));
  const actualSequence = actualIds.filter((id) => plannedSet.has(id));
  const outOfOrder = plannedSequence.join(',') !== actualSequence.join(',');
  const arrivalRate = plannedIds.length
    ? Math.round(((plannedIds.length - missed.length) / plannedIds.length) * 1000) / 10
    : 0;

  let level = '轻微偏离';
  if (!missed.length && !extra.length && !outOfOrder) {
    level = '无偏离';
  } else if (arrivalRate < ARRIVAL_RATE_SIGNIFICANT_THRESHOLD || missed.length >= MISSED_SIGNIFICANT_THRESHOLD) {
    level = '明显偏离';
  }
  return { arrivalRate, missed, extra, outOfOrder, level };
}

/** 两个 datetime 值之间的分钟数，非法输入返回 null。 */
export function stayMinutes(arrive, leave) {
  if (!arrive || !leave) return null;
  const diff = new Date(leave).getTime() - new Date(arrive).getTime();
  if (Number.isNaN(diff) || diff < 0) return null;
  return Math.round(diff / 60000);
}

/** 把分钟数格式化为「X小时X分」。 */
export function formatMinutes(minutes) {
  if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) return '-';
  const total = Math.round(Number(minutes));
  if (total < 60) return `${total}分钟`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${hours}小时${rest}分` : `${hours}小时`;
}
