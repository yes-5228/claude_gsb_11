import { useState } from 'react';

import { patrolPlanApi, patrolRecordApi } from '../../api/patrols.js';
import { restroomApi } from '../../api/restrooms.js';
import DataTable from '../../components/DataTable.jsx';
import Field from '../../components/Field.jsx';
import PageHeader from '../../components/PageHeader.jsx';
import Pagination from '../../components/Pagination.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useAsync } from '../../hooks/useAsync.js';
import { useDictionaries } from '../../hooks/useDictionaries.js';
import { useListQuery } from '../../hooks/useListQuery.js';
import { formatDateTime } from '../../utils/format.js';
import { deviationTone, formatMinutes } from '../../utils/patrol.js';
import PatrolPlanFormModal from './PatrolPlanFormModal.jsx';
import PatrolRecordDetailModal from './PatrolRecordDetailModal.jsx';
import PatrolRecordFormModal from './PatrolRecordFormModal.jsx';

const RECORD_FILTERS = { keyword: '', plan_id: '', deviation_level: '', date_from: '', date_to: '' };
const PLAN_FILTERS = { keyword: '', district: '' };

const TABS = [
  { key: 'records', label: '巡查记录' },
  { key: 'plans', label: '计划路线' },
];

export default function PatrolListPage() {
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const [tab, setTab] = useState('records');
  const [planForm, setPlanForm] = useState(null); // null | { plan? }
  const [recordFormOpen, setRecordFormOpen] = useState(false);
  const [activeRecord, setActiveRecord] = useState(null);

  const records = useListQuery((params) => patrolRecordApi.list(params), RECORD_FILTERS, 10);
  const plans = useListQuery((params) => patrolPlanApi.list(params), PLAN_FILTERS, 10);
  const { data: planOptions, reload: reloadPlanOptions } = useAsync(
    () => patrolPlanApi.list({ page_size: 100 }),
    [],
  );
  const { data: districts } = useAsync(() => restroomApi.districts(), []);

  const reloadAll = () => {
    records.reload();
    plans.reload();
    reloadPlanOptions();
  };

  const removeRecord = async (row) => {
    if (!window.confirm('确认删除该条巡查路线记录？')) return;
    try {
      await patrolRecordApi.remove(row.id);
      toast.success('删除成功');
      records.reload();
      reloadPlanOptions();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const removePlan = async (row) => {
    if (!window.confirm(`确认删除计划路线「${row.name}」？`)) return;
    try {
      await patrolPlanApi.remove(row.id);
      toast.success('删除成功');
      reloadAll();
    } catch (err) {
      if (err.status === 409 && window.confirm(`${err.message}，是否连同巡查记录一并删除？`)) {
        try {
          await patrolPlanApi.remove(row.id, true);
          toast.success('已强制删除');
          reloadAll();
        } catch (forceErr) {
          toast.error(forceErr.message);
        }
      } else if (err.status !== 409) {
        toast.error(err.message);
      }
    }
  };

  return (
    <>
      <PageHeader
        title="巡查路线"
        description="计划路线与实际轨迹比对，自动计算到位率与偏离情况，明显偏离需补充说明"
        actions={
          tab === 'records' ? (
            <button type="button" className="btn btn-primary" onClick={() => setRecordFormOpen(true)}>
              + 新增巡查记录
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setPlanForm({ plan: null })}
            >
              + 新增计划路线
            </button>
          )
        }
      />
      <div className="content">
        <div className="inline" style={{ marginBottom: 12 }}>
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`btn btn-sm${tab === item.key ? ' btn-primary' : ''}`}
              onClick={() => setTab(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {tab === 'records' ? (
          <>
            <section className="card">
              <div className="filter-bar">
                <Field label="关键字" full>
                  <input
                    value={records.filters.keyword}
                    placeholder="路线名称 / 巡查人 / 偏离说明"
                    onChange={(event) => records.updateFilter('keyword', event.target.value)}
                  />
                </Field>
                <Field label="计划路线">
                  <select
                    value={records.filters.plan_id}
                    onChange={(event) => records.updateFilter('plan_id', event.target.value)}
                  >
                    <option value="">全部</option>
                    {(planOptions?.items || []).map((plan) => (
                      <option key={plan.id} value={plan.id}>
                        {plan.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="偏离程度">
                  <select
                    value={records.filters.deviation_level}
                    onChange={(event) => records.updateFilter('deviation_level', event.target.value)}
                  >
                    <option value="">全部</option>
                    {(dictionaries?.patrol_deviation_level || []).map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                </Field>
                <Field label="开始日期">
                  <input
                    type="date"
                    value={records.filters.date_from}
                    onChange={(event) => records.updateFilter('date_from', event.target.value)}
                  />
                </Field>
                <Field label="结束日期">
                  <input
                    type="date"
                    value={records.filters.date_to}
                    onChange={(event) => records.updateFilter('date_to', event.target.value)}
                  />
                </Field>
                <button type="button" className="btn" onClick={records.resetFilters}>
                  重置
                </button>
              </div>
            </section>

            <section className="card">
              <DataTable
                loading={records.loading}
                error={records.error}
                rows={records.items}
                emptyText="暂无巡查路线记录"
                columns={[
                  {
                    key: 'start_time',
                    title: '开始时间',
                    render: (row) => formatDateTime(row.start_time),
                  },
                  { key: 'plan_name', title: '计划路线' },
                  { key: 'inspector', title: '巡查人' },
                  {
                    key: 'duration',
                    title: '巡查耗时',
                    render: (row) => formatMinutes(row.duration_minutes),
                  },
                  {
                    key: 'tracks',
                    title: '经过点位',
                    render: (row) => `${row.tracks?.length ?? 0} 个`,
                  },
                  {
                    key: 'arrival_rate',
                    title: '到位率',
                    render: (row) => `${row.arrival_rate}%`,
                  },
                  {
                    key: 'deviation_level',
                    title: '偏离情况',
                    render: (row) => (
                      <span className={`tag ${deviationTone(row.deviation_level)}`}>
                        {row.deviation_level}
                      </span>
                    ),
                  },
                  {
                    key: 'deviation_note',
                    title: '偏离说明',
                    render: (row) =>
                      row.deviation_note ? (
                        <span className="tag tag-success">已说明</span>
                      ) : row.deviation_level === '明显偏离' ? (
                        <span className="tag tag-danger">待补充</span>
                      ) : (
                        '-'
                      ),
                  },
                  {
                    key: 'actions',
                    title: '操作',
                    render: (row) => (
                      <div className="inline">
                        <button type="button" className="btn-link" onClick={() => setActiveRecord(row)}>
                          详情
                        </button>
                        <button
                          type="button"
                          className="btn-link danger"
                          onClick={() => removeRecord(row)}
                        >
                          删除
                        </button>
                      </div>
                    ),
                  },
                ]}
              />
              <Pagination meta={records.meta} onPageChange={records.setPage} />
            </section>
          </>
        ) : (
          <>
            <section className="card">
              <div className="filter-bar">
                <Field label="关键字" full>
                  <input
                    value={plans.filters.keyword}
                    placeholder="路线名称 / 备注"
                    onChange={(event) => plans.updateFilter('keyword', event.target.value)}
                  />
                </Field>
                <Field label="所属区域">
                  <select
                    value={plans.filters.district}
                    onChange={(event) => plans.updateFilter('district', event.target.value)}
                  >
                    <option value="">全部</option>
                    {(districts || []).map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                </Field>
                <button type="button" className="btn" onClick={plans.resetFilters}>
                  重置
                </button>
              </div>
            </section>

            <section className="card">
              <DataTable
                loading={plans.loading}
                error={plans.error}
                rows={plans.items}
                emptyText="暂无计划路线，点击右上角新增"
                columns={[
                  { key: 'name', title: '路线名称' },
                  { key: 'district', title: '区域' },
                  { key: 'inspector', title: '计划巡查人' },
                  { key: 'shift', title: '班次' },
                  {
                    key: 'points',
                    title: '途经点位',
                    render: (row) => (
                      <span className="muted">
                        {(row.points || []).map((point) => point.restroom_name).join(' → ')}
                      </span>
                    ),
                  },
                  { key: 'record_count', title: '巡查次数' },
                  {
                    key: 'actions',
                    title: '操作',
                    render: (row) => (
                      <div className="inline">
                        <button
                          type="button"
                          className="btn-link"
                          onClick={() => setPlanForm({ plan: row })}
                        >
                          编辑
                        </button>
                        <button
                          type="button"
                          className="btn-link danger"
                          onClick={() => removePlan(row)}
                        >
                          删除
                        </button>
                      </div>
                    ),
                  },
                ]}
              />
              <Pagination meta={plans.meta} onPageChange={plans.setPage} />
            </section>
          </>
        )}
      </div>

      {planForm ? (
        <PatrolPlanFormModal
          plan={planForm.plan}
          onClose={() => setPlanForm(null)}
          onSaved={reloadAll}
        />
      ) : null}

      {recordFormOpen ? (
        <PatrolRecordFormModal onClose={() => setRecordFormOpen(false)} onSaved={reloadAll} />
      ) : null}

      {activeRecord ? (
        <PatrolRecordDetailModal
          record={activeRecord}
          onClose={() => setActiveRecord(null)}
          onSaved={(updated) => {
            setActiveRecord(updated);
            records.reload();
          }}
        />
      ) : null}
    </>
  );
}
