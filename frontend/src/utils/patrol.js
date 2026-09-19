/**
 * 巡查路线比对的前端预览实现，规则与后端 app/services/patrol_service.py 保持一致，
 * 用于表单内实时提示到位率与偏离项；最终以服务端计算结果为准。
 */

export const ARRIVAL_RATE_THRESHOLD = 80;
export const STAY_TOLERANCE_MINUTES = 1;

/**
 * @param plannedPoints 计划点位 [{restroom_id, stay_minutes, restroom_name}]
 * @param actualPoints 实际轨迹 [{restroom_id, point_name, arrive_at: Date, leave_at: Date}]
 */
export function compareRoute(plannedPoints, actualPoints) {
  const deviations = [];
  const plannedIds = plannedPoints.map((point) => point.restroom_id);
  const plannedMap = new Map(plannedPoints.map((point) => [point.restroom_id, point]));

  const actualPlanned = [];
  actualPoints.forEach((actual) => {
    if (plannedMap.has(actual.restroom_id)) {
      actualPlanned.push(actual);
    } else {
      deviations.push({
        type: '计划外点位',
        point_name: actual.point_name,
        detail: '该点位不在计划路线中',
      });
    }
  });

  const arrivedIds = new Set(actualPlanned.map((actual) => actual.restroom_id));

  plannedPoints.forEach((planned) => {
    if (!arrivedIds.has(planned.restroom_id)) {
      deviations.push({
        type: '漏巡',
        point_name: planned.restroom_name,
        detail: '计划点位未巡查',
      });
      return;
    }
    const actual = actualPlanned.find((item) => item.restroom_id === planned.restroom_id);
    const stay = (actual.leave_at - actual.arrive_at) / 60000;
    if (stay < planned.stay_minutes - STAY_TOLERANCE_MINUTES) {
      deviations.push({
        type: '停留不足',
        point_name: planned.restroom_name,
        detail: `计划停留 ${planned.stay_minutes} 分钟，实际停留 ${Math.floor(stay)} 分钟`,
      });
    }
  });

  const visitedOrder = [...actualPlanned]
    .sort((a, b) => a.arrive_at - b.arrive_at)
    .map((actual) => actual.restroom_id);
  const expectedOrder = plannedIds.filter((id) => arrivedIds.has(id));
  if (visitedOrder.join(',') !== expectedOrder.join(',')) {
    deviations.push({ type: '顺序偏离', point_name: '', detail: '实际巡查顺序与计划路线不一致' });
  }

  const plannedCount = plannedPoints.length;
  const arrivedCount = arrivedIds.size;
  const arrivalRate = plannedCount
    ? Math.round((arrivedCount / plannedCount) * 1000) / 10
    : 0;
  const isDeviated =
    arrivalRate < ARRIVAL_RATE_THRESHOLD || deviations.some((item) => item.type === '漏巡');

  return { plannedCount, arrivedCount, arrivalRate, deviations, isDeviated };
}
