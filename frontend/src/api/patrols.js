import { http } from './client.js';

const PLANS = '/patrol-plans';
const RECORDS = '/patrol-records';

export const patrolPlanApi = {
  list: (params) => http.get(PLANS, params),
  detail: (id) => http.get(`${PLANS}/${id}`),
  create: (payload) => http.post(PLANS, payload),
  update: (id, payload) => http.patch(`${PLANS}/${id}`, payload),
  remove: (id, force) => http.delete(`${PLANS}/${id}`, force ? { force: true } : undefined),
};

export const patrolRecordApi = {
  list: (params) => http.get(RECORDS, params),
  detail: (id) => http.get(`${RECORDS}/${id}`),
  create: (payload) => http.post(RECORDS, payload),
  update: (id, payload) => http.patch(`${RECORDS}/${id}`, payload),
  remove: (id) => http.delete(`${RECORDS}/${id}`),
};
