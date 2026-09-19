import { useEffect, useMemo, useState } from 'react';

import { metaApi } from '../../api/meta.js';
import { patrolApi } from '../../api/patrols.js';
import Field from '../../components/Field.jsx';
import Modal from '../../components/Modal.jsx';
import { useToast } from '../../components/Toast.jsx';
import { deviationTone, toDateTimeInput } from '../../utils/format.js';
import { compareRoute } from '../../utils/patrol.js';

const TRAVEL_MINUTES = 10;

/** 按计划路线生成一份默认打卡时间：每点位间隔 10 分钟路程，停留即计划时长。 */
function buildSchedule(route, startTime) {
  const start = startTime ? new Date(startTime) : new Date();
  let cursor = Number.isNaN(start.getTime()) ? new Date() : start;
  return route.points.map((point) => {
    const arrive = new Date(cursor.getTime() + TRAVEL_MINUTES * 60000);
    const leave = new Date(arrive.getTime() + point.stay_minutes * 60000);
    cursor = leave;
    return {
      restroom_id: point.restroom_id,
      point_name: point.restroom_name,
      stay_minutes: point.stay_minutes,
      planned: true,
      missed: false,
      arrive: toDateTimeInput(arrive),
      leave: toDateTimeInput(leave),
    };
  });
}

export default function RecordFormModal({ onClose, onSaved }) {
  const toast = useToast();
  const [routes, setRoutes] = useState([]);
  const [restroomOptions, setRestroomOptions] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({
    route_id: '',
    inspector: '',
    start_time: toDateTimeInput(),
    end_time: '',
    deviation_note: '',
  });
  const [rows, setRows] = useState([]);

  useEffect(() => {
    Promise.all([patrolApi.listRoutes({ enabled: true }), metaApi.restroomOptions()])
      .then(([routeList, options]) => {
        setRoutes(routeList);
        setRestroomOptions(options);
      })
      .catch((err) => setError(err.message));
  }, []);

  const route = useMemo(
    () => routes.find((item) => item.id === Number(form.route_id)) || null,
    [routes, form.route_id],
  );

  const selectRoute = (routeId) => {
    const target = routes.find((item) => item.id === Number(routeId));
    if (!target) {
      setForm((prev) => ({ ...prev, route_id: routeId }));
      setRows([]);
      return;
    }
    const schedule = buildSchedule(target, form.start_time);
    const last = schedule[schedule.length - 1];
    setRows(schedule);
    setForm((prev) => ({
      ...prev,
      route_id: routeId,
      end_time: last ? last.leave : prev.end_time,
    }));
  };

  const updateRow = (index, patch) => {
    setRows((prev) => prev.map((row, idx) => (idx === index ? { ...row, ...patch } : row)));
  };

  const addExtraRow = () => {
    setRows((prev) => [
      ...prev,
      {
        restroom_id: '',
        point_name: '',
        stay_minutes: 0,
        planned: false,
        missed: false,
        arrive: toDateTimeInput(),
        leave: toDateTimeInput(),
      },
    ]);
  };

  const removeRow = (index) => setRows((prev) => prev.filter((_, idx) => idx !== index));

  // 实时比对预览：与后端规则一致，提交时以服务端结果为准
  const preview = useMemo(() => {
    if (!route) return null;
    const actualPoints = rows
      .filter((row) => !row.missed && row.restroom_id && row.arrive && row.leave)
      .map((row) => ({
        restroom_id: Number(row.restroom_id),
        point_name: row.point_name || row.restroom_id,
        arrive_at: new Date(row.arrive),
        leave_at: new Date(row.leave),
      }))
      .filter((row) => !Number.isNaN(row.arrive_at.getTime()) && !Number.isNaN(row.leave_at.getTime()));
    return compareRoute(route.points, actualPoints);
  }, [route, rows]);

  const submit = async (event) => {
    event.preventDefault();
    if (!form.route_id) {
      setError('请选择巡查路线');
      return;
    }
    if (!form.inspector.trim()) {
      setError('请填写巡查人');
      return;
    }
    if (!form.start_time || !form.end_time) {
      setError('请填写巡查开始与结束时间');
      return;
    }
    if (new Date(form.end_time) < new Date(form.start_time)) {
      setError('结束时间不能早于开始时间');
      return;
    }
    const actualPoints = rows
      .filter((row) => !row.missed && row.restroom_id && row.arrive && row.leave)
      .map((row) => ({
        restroom_id: Number(row.restroom_id),
        arrive_at: new Date(row.arrive).toISOString(),
        leave_at: new Date(row.leave).toISOString(),
      }));
    if (preview?.isDeviated && !form.deviation_note.trim()) {
      setError(`本次巡查到位率 ${preview.arrivalRate}%，存在明显偏离，请填写偏离说明`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await patrolApi.createRecord({
        route_id: Number(form.route_id),
        inspector: form.inspector.trim(),
        start_time: new Date(form.start_time).toISOString(),
        end_time: new Date(form.end_time).toISOString(),
        actual_points: actualPoints,
        deviation_note: form.deviation_note.trim() || null,
      });
      toast.success('巡查执行记录已提交');
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="登记巡查执行记录"
      onClose={onClose}
      width={920}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button type="submit" form="patrol-record-form" className="btn btn-primary" disabled={saving}>
            {saving ? '提交中…' : '提交记录'}
          </button>
        </>
      }
    >
      {error ? <div className="alert alert-error">{error}</div> : null}
      <form id="patrol-record-form" onSubmit={submit} className="form-grid">
        <Field label="巡查路线 *">
          <select value={form.route_id} onChange={(event) => selectRoute(event.target.value)}>
            <option value="">请选择路线</option>
            {routes.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}（{item.district} · {item.points.length} 个点位）
              </option>
            ))}
          </select>
        </Field>
        <Field label="巡查人 *">
          <input
            value={form.inspector}
            onChange={(event) => setForm((prev) => ({ ...prev, inspector: event.target.value }))}
            placeholder="请输入巡查人姓名"
          />
        </Field>
        <Field label="开始时间 *">
          <input
            type="datetime-local"
            value={form.start_time}
            onChange={(event) => setForm((prev) => ({ ...prev, start_time: event.target.value }))}
          />
        </Field>
        <Field label="结束时间 *">
          <input
            type="datetime-local"
            value={form.end_time}
            onChange={(event) => setForm((prev) => ({ ...prev, end_time: event.target.value }))}
          />
        </Field>
      </form>

      {route ? (
        <>
          <div className="card-title">
            <div className="inline">
              <h3>点位打卡</h3>
              <span className="muted">勾选「未巡」表示该计划点位未到访；可追加计划外点位</span>
            </div>
            <div className="inline">
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => {
                  const schedule = buildSchedule(route, form.start_time);
                  setRows((prev) => [...schedule, ...prev.filter((row) => !row.planned)]);
                }}
              >
                按计划重排时间
              </button>
              <button type="button" className="btn btn-sm" onClick={addExtraRow}>
                + 计划外点位
              </button>
            </div>
          </div>

          <div className="checkin-table">
            <div className="checkin-head">
              <span>#</span>
              <span>点位</span>
              <span>计划停留</span>
              <span>到达时间</span>
              <span>离开时间</span>
              <span>未巡</span>
              <span />
            </div>
            {rows.map((row, index) => (
              <div
                className={`checkin-row${row.missed ? ' is-missed' : ''}${row.planned ? '' : ' is-extra'}`}
                key={index}
              >
                <span className="order">{index + 1}</span>
                {row.planned ? (
                  <span className="point-name">{row.point_name}</span>
                ) : (
                  <select
                    value={row.restroom_id}
                    onChange={(event) => {
                      const option = restroomOptions.find(
                        (item) => item.id === Number(event.target.value),
                      );
                      updateRow(index, {
                        restroom_id: event.target.value,
                        point_name: option ? option.name : '',
                      });
                    }}
                  >
                    <option value="">选择公厕</option>
                    {restroomOptions.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.code} {option.name}
                      </option>
                    ))}
                  </select>
                )}
                <span className="muted">{row.planned ? `${row.stay_minutes} 分钟` : '计划外'}</span>
                <input
                  type="datetime-local"
                  value={row.arrive}
                  disabled={row.missed}
                  onChange={(event) => updateRow(index, { arrive: event.target.value })}
                />
                <input
                  type="datetime-local"
                  value={row.leave}
                  disabled={row.missed}
                  onChange={(event) => updateRow(index, { leave: event.target.value })}
                />
                {row.planned ? (
                  <input
                    type="checkbox"
                    checked={row.missed}
                    onChange={(event) => updateRow(index, { missed: event.target.checked })}
                  />
                ) : (
                  <span />
                )}
                {row.planned ? (
                  <span />
                ) : (
                  <button type="button" className="btn-link danger" onClick={() => removeRow(index)}>
                    移除
                  </button>
                )}
              </div>
            ))}
          </div>

          {preview ? (
            <div className={`alert ${preview.isDeviated ? 'alert-error' : 'alert-info'}`}>
              <div className="inline" style={{ flexWrap: 'wrap' }}>
                <strong>
                  比对预览：到位 {preview.arrivedCount}/{preview.plannedCount}，到位率{' '}
                  {preview.arrivalRate}%
                </strong>
                {preview.isDeviated ? <span className="tag tag-danger">偏离明显</span> : null}
                {preview.deviations.map((item, index) => (
                  <span key={index} className={`tag ${deviationTone(item.type)}`}>
                    {item.type}
                    {item.point_name ? `·${item.point_name}` : ''}
                  </span>
                ))}
                {!preview.deviations.length ? <span className="tag tag-success">无偏离</span> : null}
              </div>
            </div>
          ) : null}

          <Field
            label={preview?.isDeviated ? '偏离说明 *（偏离明显，必填）' : '偏离说明'}
            full
            hint="到位率低于 80% 或存在漏巡点位时，必须说明原因"
          >
            <textarea
              rows="2"
              value={form.deviation_note}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, deviation_note: event.target.value }))
              }
              placeholder="偏离明显时请说明原因，例如：道路施工绕行、突发任务等"
            />
          </Field>
        </>
      ) : (
        <div className="empty-block">请先选择巡查路线，系统将按计划点位生成打卡表</div>
      )}
    </Modal>
  );
}
