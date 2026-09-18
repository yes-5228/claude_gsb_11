import { useEffect, useMemo, useState } from 'react';

import { metaApi } from '../../api/meta.js';
import { patrolPlanApi, patrolRecordApi } from '../../api/patrols.js';
import Field from '../../components/Field.jsx';
import Modal from '../../components/Modal.jsx';
import { useToast } from '../../components/Toast.jsx';
import { toDateTimeInput } from '../../utils/format.js';
import { compareRoute, deviationTone, formatMinutes, stayMinutes } from '../../utils/patrol.js';

const TRANSIT_MINUTES = 8;

export default function PatrolRecordFormModal({ onClose, onSaved }) {
  const toast = useToast();
  const [plans, setPlans] = useState([]);
  const [options, setOptions] = useState([]);
  const [form, setForm] = useState({
    plan_id: '',
    inspector: '',
    start_time: toDateTimeInput(),
    end_time: '',
    deviation_note: '',
    remark: '',
  });
  const [tracks, setTracks] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    patrolPlanApi
      .list({ page_size: 100 })
      .then((page) => setPlans(page.items || []))
      .catch((err) => setError(err.message));
    metaApi
      .restroomOptions()
      .then(setOptions)
      .catch((err) => setError(err.message));
  }, []);

  const plan = useMemo(
    () => plans.find((item) => item.id === Number(form.plan_id)) || null,
    [plans, form.plan_id],
  );

  // 实时比对预览：计划点位 vs 当前轨迹（仅统计已选择公厕的行）
  const preview = useMemo(() => {
    if (!plan) return null;
    const plannedIds = (plan.points || []).map((point) => point.restroom_id);
    const actualIds = tracks.filter((row) => row.restroom_id).map((row) => Number(row.restroom_id));
    return compareRoute(plannedIds, actualIds);
  }, [plan, tracks]);

  const restroomName = (id) => options.find((item) => item.id === Number(id))?.name || `公厕#${id}`;

  const setValue = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const selectPlan = (event) => {
    const planId = event.target.value;
    const selected = plans.find((item) => item.id === Number(planId));
    setForm((prev) => ({
      ...prev,
      plan_id: planId,
      inspector: prev.inspector || selected?.inspector || '',
    }));
    // 按计划点位预置轨迹行，到离时间留空由巡查人填写
    setTracks(
      (selected?.points || []).map((point) => ({
        restroom_id: point.restroom_id,
        arrive_time: '',
        leave_time: '',
      })),
    );
  };

  const setTrack = (index, key, value) =>
    setTracks((prev) => prev.map((row, idx) => (idx === index ? { ...row, [key]: value } : row)));

  /** 按计划点位顺序与停留时长，从开始时间自动铺出整条轨迹。 */
  const prefillTracks = () => {
    if (!plan || !form.start_time) {
      setError('请先选择计划路线并填写开始时间');
      return;
    }
    let cursor = new Date(form.start_time).getTime();
    const rows = (plan.points || []).map((point) => {
      const arrive = cursor + TRANSIT_MINUTES * 60000;
      const leave = arrive + (Number(point.stay_minutes) || 15) * 60000;
      cursor = leave;
      return {
        restroom_id: point.restroom_id,
        arrive_time: toDateTimeInput(new Date(arrive)),
        leave_time: toDateTimeInput(new Date(leave)),
      };
    });
    setTracks(rows);
    setForm((prev) => ({
      ...prev,
      end_time: toDateTimeInput(new Date(cursor + 5 * 60000)),
    }));
    setError(null);
  };

  const validate = () => {
    if (!form.plan_id) return '请选择计划路线';
    if (!form.inspector.trim()) return '请填写巡查人';
    if (!form.start_time || !form.end_time) return '请填写巡查开始与结束时间';
    const start = new Date(form.start_time).getTime();
    const end = new Date(form.end_time).getTime();
    if (end <= start) return '巡查结束时间必须晚于开始时间';
    if (!tracks.length) return '请至少添加一个轨迹点位';
    const ids = [];
    for (const row of tracks) {
      if (!row.restroom_id) return '存在未选择公厕的轨迹点位';
      if (!row.arrive_time || !row.leave_time) return '轨迹点位需填写到达与离开时间';
      const arrive = new Date(row.arrive_time).getTime();
      const leave = new Date(row.leave_time).getTime();
      if (leave < arrive) return '轨迹点位的离开时间不能早于到达时间';
      if (arrive < start || leave > end) return '轨迹点位的到离时间需位于巡查起止时间内';
      ids.push(Number(row.restroom_id));
    }
    if (new Set(ids).size !== ids.length) return '同一公厕在轨迹中重复出现';
    if (preview?.level === '明显偏离' && !form.deviation_note.trim()) {
      return '本次巡查与计划路线偏离明显，需补充偏离说明';
    }
    return null;
  };

  const submit = async (event) => {
    event.preventDefault();
    const message = validate();
    if (message) {
      setError(message);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await patrolRecordApi.create({
        plan_id: Number(form.plan_id),
        inspector: form.inspector.trim(),
        start_time: new Date(form.start_time).toISOString(),
        end_time: new Date(form.end_time).toISOString(),
        tracks: tracks.map((row) => ({
          restroom_id: Number(row.restroom_id),
          arrive_time: new Date(row.arrive_time).toISOString(),
          leave_time: new Date(row.leave_time).toISOString(),
        })),
        deviation_note: form.deviation_note.trim() || null,
        remark: form.remark.trim() || null,
      });
      toast.success('巡查路线记录已提交');
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
      title="新增巡查路线记录"
      onClose={onClose}
      width={920}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button
            type="submit"
            form="patrol-record-form"
            className="btn btn-primary"
            disabled={saving}
          >
            {saving ? '提交中…' : '提交记录'}
          </button>
        </>
      }
    >
      {error ? <div className="alert alert-error">{error}</div> : null}
      <form id="patrol-record-form" onSubmit={submit} className="form-grid">
        <Field label="计划路线 *">
          <select value={form.plan_id} onChange={selectPlan}>
            <option value="">请选择计划路线</option>
            {plans.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}（{item.district} / {item.shift}）
              </option>
            ))}
          </select>
        </Field>
        <Field label="巡查人 *">
          <input
            value={form.inspector}
            onChange={setValue('inspector')}
            placeholder="实际巡查人姓名"
          />
        </Field>
        <Field label="巡查开始时间 *">
          <input
            type="datetime-local"
            value={form.start_time}
            onChange={setValue('start_time')}
          />
        </Field>
        <Field label="巡查结束时间 *">
          <input type="datetime-local" value={form.end_time} onChange={setValue('end_time')} />
        </Field>
      </form>

      <div className="card-title">
        <div className="inline">
          <h3>实际轨迹（按到访顺序）</h3>
          {preview ? (
            <>
              <span className="tag tag-primary">到位率 {preview.arrivalRate}%</span>
              <span className={`tag ${deviationTone(preview.level)}`}>{preview.level}</span>
            </>
          ) : null}
        </div>
        <div className="inline">
          <button type="button" className="btn btn-sm" onClick={prefillTracks}>
            按计划预填轨迹
          </button>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() =>
              setTracks((prev) => [...prev, { restroom_id: '', arrive_time: '', leave_time: '' }])
            }
          >
            + 添加点位
          </button>
        </div>
      </div>

      {preview && (preview.missed.length > 0 || preview.extra.length > 0 || preview.outOfOrder) ? (
        <div className={`alert ${preview.level === '明显偏离' ? 'alert-error' : 'alert-info'}`}>
          {preview.missed.length ? (
            <div>漏巡点位：{preview.missed.map(restroomName).join('、')}</div>
          ) : null}
          {preview.extra.length ? (
            <div>计划外点位：{preview.extra.map(restroomName).join('、')}</div>
          ) : null}
          {preview.outOfOrder ? <div>到访顺序与计划路线不一致</div> : null}
        </div>
      ) : null}

      {tracks.length ? (
        <div className="track-editor">
          <div className="track-row track-row-head">
            <span>公厕点位</span>
            <span>到达时间</span>
            <span>离开时间</span>
            <span>停留</span>
            <span>操作</span>
          </div>
          {tracks.map((row, index) => {
            const stay = stayMinutes(row.arrive_time, row.leave_time);
            return (
              <div className="track-row" key={index}>
                <select
                  value={row.restroom_id}
                  onChange={(event) => setTrack(index, 'restroom_id', event.target.value)}
                >
                  <option value="">请选择公厕</option>
                  {options.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.code} {option.name}
                    </option>
                  ))}
                </select>
                <input
                  type="datetime-local"
                  value={row.arrive_time}
                  onChange={(event) => setTrack(index, 'arrive_time', event.target.value)}
                />
                <input
                  type="datetime-local"
                  value={row.leave_time}
                  onChange={(event) => setTrack(index, 'leave_time', event.target.value)}
                />
                <span className="muted">{stay === null ? '-' : formatMinutes(stay)}</span>
                <button
                  type="button"
                  className="btn-link danger"
                  onClick={() => setTracks((prev) => prev.filter((_, idx) => idx !== index))}
                >
                  删除
                </button>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty-block">选择计划路线后自动带出点位，也可手动添加</div>
      )}

      <div className="form-grid" style={{ marginTop: 12 }}>
        <Field
          label={preview?.level === '明显偏离' ? '偏离说明 *（明显偏离必填）' : '偏离说明'}
          full
          hint="与计划路线存在偏离时填写原因，明显偏离为必填"
        >
          <textarea
            rows="2"
            value={form.deviation_note}
            onChange={setValue('deviation_note')}
            placeholder="如：沿线施工围挡，临时跳过封闭点位"
          />
        </Field>
        <Field label="备注" full>
          <textarea
            rows="2"
            value={form.remark}
            onChange={setValue('remark')}
            placeholder="选填"
          />
        </Field>
      </div>
    </Modal>
  );
}
