import { useState } from 'react';

import { patrolApi } from '../../api/patrols.js';
import { restroomApi } from '../../api/restrooms.js';
import DataTable from '../../components/DataTable.jsx';
import Field from '../../components/Field.jsx';
import PageHeader from '../../components/PageHeader.jsx';
import Pagination from '../../components/Pagination.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useAsync } from '../../hooks/useAsync.js';
import { useDictionaries } from '../../hooks/useDictionaries.js';
import { useListQuery } from '../../hooks/useListQuery.js';
import {
  arrivalRateTone,
  deviationTone,
  formatDateTime,
  formatDuration,
} from '../../utils/format.js';
import RecordDetailModal from './RecordDetailModal.jsx';
import RecordFormModal from './RecordFormModal.jsx';
import RouteFormModal from './RouteFormModal.jsx';

const TABS = [
  { key: 'records', label: '巡查执行记录' },
  { key: 'routes', label: '路线计划' },
];

const DEFAULT_FILTERS = {
  keyword: '',
  district: '',
  route_id: '',
  is_deviated: '',
  date_from: '',
  date_to: '',
};

function RecordsTab({ routes, districts, reloadRoutes }) {
  const toast = useToast();
  const [showForm, setShowForm] = useState(false);
  const [active, setActive] = useState(null);
  const list = useListQuery((params) => patrolApi.listRecords(params), DEFAULT_FILTERS, 10);

  const remove = async (row) => {
    if (!window.confirm(`确认删除 ${formatDateTime(row.start_time)} 的巡查执行记录？`)) return;
    try {
      await patrolApi.removeRecord(row.id);
      toast.success('删除成功');
      list.reload();
      reloadRoutes();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <>
      <section className="card">
        <div className="filter-bar">
          <Field label="关键字" full>
            <input
              value={list.filters.keyword}
              placeholder="路线名称 / 巡查人 / 偏离说明"
              onChange={(event) => list.updateFilter('keyword', event.target.value)}
            />
          </Field>
          <Field label="所属区域">
            <select
              value={list.filters.district}
              onChange={(event) => list.updateFilter('district', event.target.value)}
            >
              <option value="">全部</option>
              {(districts || []).map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </Field>
          <Field label="巡查路线">
            <select
              value={list.filters.route_id}
              onChange={(event) => list.updateFilter('route_id', event.target.value)}
            >
              <option value="">全部</option>
              {(routes || []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="偏离情况">
            <select
              value={list.filters.is_deviated}
              onChange={(event) => list.updateFilter('is_deviated', event.target.value)}
            >
              <option value="">全部</option>
              <option value="true">偏离明显</option>
              <option value="false">正常</option>
            </select>
          </Field>
          <Field label="开始日期">
            <input
              type="date"
              value={list.filters.date_from}
              onChange={(event) => list.updateFilter('date_from', event.target.value)}
            />
          </Field>
          <Field label="结束日期">
            <input
              type="date"
              value={list.filters.date_to}
              onChange={(event) => list.updateFilter('date_to', event.target.value)}
            />
          </Field>
          <button type="button" className="btn" onClick={list.resetFilters}>
            重置
          </button>
        </div>
      </section>

      <section className="card">
        <div className="card-title">
          <h3>巡查执行记录</h3>
          <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
            + 登记巡查记录
          </button>
        </div>
        <DataTable
          loading={list.loading}
          error={list.error}
          rows={list.items}
          emptyText="暂无巡查执行记录"
          columns={[
            {
              key: 'start_time',
              title: '巡查时间',
              render: (row) => (
                <div>
                  <div>{formatDateTime(row.start_time)}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    至 {formatDateTime(row.end_time)} · 用时 {formatDuration(row.duration_minutes)}
                  </div>
                </div>
              ),
            },
            { key: 'route_name', title: '巡查路线' },
            { key: 'inspector', title: '巡查人' },
            {
              key: 'arrival_rate',
              title: '到位率',
              render: (row) => (
                <span className={`tag ${arrivalRateTone(row.arrival_rate)}`}>
                  {row.arrival_rate}%（{row.arrived_count}/{row.planned_count}）
                </span>
              ),
            },
            {
              key: 'deviations',
              title: '偏离情况',
              render: (row) =>
                row.deviations.length ? (
                  <div className="inline" style={{ flexWrap: 'wrap' }}>
                    {[...new Set(row.deviations.map((item) => item.type))].map((type) => (
                      <span key={type} className={`tag ${deviationTone(type)}`}>
                        {type}
                      </span>
                    ))}
                    {row.is_deviated ? <span className="tag tag-danger">偏离明显</span> : null}
                  </div>
                ) : (
                  <span className="tag tag-success">无偏离</span>
                ),
            },
            {
              key: 'deviation_note',
              title: '偏离说明',
              render: (row) =>
                row.deviation_note ? (
                  <span title={row.deviation_note}>
                    {row.deviation_note.length > 24
                      ? `${row.deviation_note.slice(0, 24)}…`
                      : row.deviation_note}
                  </span>
                ) : (
                  <span className="muted">-</span>
                ),
            },
            {
              key: 'actions',
              title: '操作',
              render: (row) => (
                <div className="inline">
                  <button type="button" className="btn-link" onClick={() => setActive(row)}>
                    详情
                  </button>
                  <button type="button" className="btn-link danger" onClick={() => remove(row)}>
                    删除
                  </button>
                </div>
              ),
            },
          ]}
        />
        <Pagination meta={list.meta} onPageChange={list.setPage} />
      </section>

      {showForm ? (
        <RecordFormModal
          onClose={() => setShowForm(false)}
          onSaved={() => {
            list.reload();
            reloadRoutes();
          }}
        />
      ) : null}
      {active ? <RecordDetailModal record={active} onClose={() => setActive(null)} /> : null}
    </>
  );
}

function RoutesTab({ routes, loading, error, reload }) {
  const toast = useToast();
  const { dictionaries } = useDictionaries();
  const [editing, setEditing] = useState(null); // null | {} | route
  const [filters, setFilters] = useState({ district: '', shift: '', enabled: '' });
  const { data: districts } = useAsync(() => restroomApi.districts(), []);

  const visible = (routes || []).filter(
    (route) =>
      (!filters.district || route.district === filters.district) &&
      (!filters.shift || route.shift === filters.shift) &&
      (filters.enabled === '' || route.enabled === (filters.enabled === '1')),
  );

  const toggleEnabled = async (route) => {
    try {
      await patrolApi.updateRoute(route.id, { enabled: !route.enabled });
      toast.success(route.enabled ? '路线已停用' : '路线已启用');
      reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const remove = async (route) => {
    const hint =
      route.record_count > 0
        ? `路线「${route.name}」已有 ${route.record_count} 条巡查记录，删除将一并清除，确认继续？`
        : `确认删除路线「${route.name}」？`;
    if (!window.confirm(hint)) return;
    try {
      await patrolApi.removeRoute(route.id, route.record_count > 0);
      toast.success('删除成功');
      reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <>
      <section className="card">
        <div className="filter-bar">
          <Field label="所属区域">
            <select
              value={filters.district}
              onChange={(event) => setFilters((prev) => ({ ...prev, district: event.target.value }))}
            >
              <option value="">全部</option>
              {(districts || []).map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </Field>
          <Field label="班次">
            <select
              value={filters.shift}
              onChange={(event) => setFilters((prev) => ({ ...prev, shift: event.target.value }))}
            >
              <option value="">全部</option>
              {(dictionaries?.shift || []).map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </Field>
          <Field label="状态">
            <select
              value={filters.enabled}
              onChange={(event) => setFilters((prev) => ({ ...prev, enabled: event.target.value }))}
            >
              <option value="">全部</option>
              <option value="1">启用</option>
              <option value="0">停用</option>
            </select>
          </Field>
        </div>
      </section>

      <section className="card">
        <div className="card-title">
          <h3>计划巡查路线</h3>
          <button type="button" className="btn btn-primary" onClick={() => setEditing({})}>
            + 新增路线
          </button>
        </div>
        <DataTable
          loading={loading}
          error={error}
          rows={visible}
          emptyText="暂无巡查路线，请先新增路线计划"
          columns={[
            { key: 'name', title: '路线名称' },
            { key: 'district', title: '区域' },
            { key: 'shift', title: '班次' },
            {
              key: 'points',
              title: '计划点位',
              render: (row) => (
                <div>
                  <span className="tag tag-primary">{row.points.length} 个点位</span>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    {row.points.map((point) => point.restroom_name).join(' → ')}
                  </div>
                </div>
              ),
            },
            {
              key: 'stay',
              title: '计划停留',
              render: (row) =>
                formatDuration(row.points.reduce((sum, point) => sum + point.stay_minutes, 0)),
            },
            {
              key: 'enabled',
              title: '状态',
              render: (row) => (
                <span className={`tag ${row.enabled ? 'tag-success' : 'tag-neutral'}`}>
                  {row.enabled ? '启用' : '停用'}
                </span>
              ),
            },
            { key: 'record_count', title: '执行记录' },
            {
              key: 'actions',
              title: '操作',
              render: (row) => (
                <div className="inline">
                  <button type="button" className="btn-link" onClick={() => setEditing(row)}>
                    编辑
                  </button>
                  <button type="button" className="btn-link" onClick={() => toggleEnabled(row)}>
                    {row.enabled ? '停用' : '启用'}
                  </button>
                  <button type="button" className="btn-link danger" onClick={() => remove(row)}>
                    删除
                  </button>
                </div>
              ),
            },
          ]}
        />
      </section>

      {editing ? (
        <RouteFormModal
          route={editing.id ? editing : null}
          onClose={() => setEditing(null)}
          onSaved={reload}
        />
      ) : null}
    </>
  );
}

export default function PatrolListPage() {
  const [tab, setTab] = useState('records');
  const {
    data: routes,
    loading: routesLoading,
    error: routesError,
    reload: reloadRoutes,
  } = useAsync(() => patrolApi.listRoutes(), []);
  const { data: districts } = useAsync(() => restroomApi.districts(), []);

  return (
    <>
      <PageHeader
        title="巡查路线追溯"
        description="按计划路线登记巡查轨迹，自动比对到位率与偏离情况，偏离明显须补充说明"
        actions={
          <div className="inline">
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
        }
      />
      <div className="content">
        {tab === 'records' ? (
          <RecordsTab routes={routes} districts={districts} reloadRoutes={reloadRoutes} />
        ) : (
          <RoutesTab
            routes={routes}
            loading={routesLoading}
            error={routesError}
            reload={reloadRoutes}
          />
        )}
      </div>
    </>
  );
}
