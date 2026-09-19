import { http } from './client.js';

export const patrolApi = {
  // 路线计划
  listRoutes: (params) => http.get('/patrol-routes', params),
  routeDetail: (id) => http.get(`/patrol-routes/${id}`),
  createRoute: (payload) => http.post('/patrol-routes', payload),
  updateRoute: (id, payload) => http.patch(`/patrol-routes/${id}`, payload),
  removeRoute: (id, force = false) => http.delete(`/patrol-routes/${id}`, force ? { force } : undefined),
  // 执行记录
  listRecords: (params) => http.get('/patrol-records', params),
  recordDetail: (id) => http.get(`/patrol-records/${id}`),
  createRecord: (payload) => http.post('/patrol-records', payload),
  removeRecord: (id) => http.delete(`/patrol-records/${id}`),
};
