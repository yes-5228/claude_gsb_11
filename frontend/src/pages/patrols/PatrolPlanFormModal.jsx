import { useEffect, useState } from 'react';

import { metaApi } from '../../api/meta.js';
import { patrolPlanApi } from '../../api/patrols.js';
import Field from '../../components/Field.jsx';
import Modal from '../../components/Modal.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useDictionaries } from '../../hooks/useDictionaries.js';

const EMPTY = { name: '', district: '', inspector: '', shift: '早班', remark: '' };

export default function PatrolPlanFormModal({ plan, onClose, onSaved }) {
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const editing = Boolean(plan?.id);
  const [options, setOptions] = useState([]);
  const [form, setForm] = useState(() => ({
    ...EMPTY,
    ...(plan
      ? {
          name: plan.name,
          district: plan.district,
          inspector: plan.inspector,
          shift: plan.shift,
          remark: plan.remark || '',
        }
      : {}),
  }));
  const [points, setPoints] = useState(() =>
    plan?.points?.length
      ? plan.points.map((point) => ({
          restroom_id: point.restroom_id,
          stay_minutes: point.stay_minutes,
        }))
      : [],
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    metaApi
      .restroomOptions()
      .then(setOptions)
      .catch((err) => setError(err.message));
  }, []);

  const setValue = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const setPoint = (index, key, value) =>
    setPoints((prev) =>
      prev.map((point, idx) => (idx === index ? { ...point, [key]: value } : point)),
    );

  const movePoint = (index, offset) =>
    setPoints((prev) => {
      const target = index + offset;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });

  const submit = async (event) => {
    event.preventDefault();
    if (!form.name.trim() || !form.district.trim() || !form.inspector.trim()) {
      setError('路线名称、所属区域、计划巡查人均为必填项');
      return;
    }
    if (!points.length) {
      setError('请至少添加一个途经点位');
      return;
    }
    if (points.some((point) => !point.restroom_id)) {
      setError('存在未选择公厕的点位');
      return;
    }
    const ids = points.map((point) => Number(point.restroom_id));
    if (new Set(ids).size !== ids.length) {
      setError('同一公厕在路线中重复出现');
      return;
    }
    setSaving(true);
    setError(null);
    const payload = {
      ...form,
      points: points.map((point) => ({
        restroom_id: Number(point.restroom_id),
        stay_minutes: Number(point.stay_minutes) || 15,
      })),
    };
    try {
      if (editing) {
        await patrolPlanApi.update(plan.id, payload);
        toast.success('计划路线已更新');
      } else {
        await patrolPlanApi.create(payload);
        toast.success('计划路线已创建');
      }
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
      title={editing ? `编辑计划路线 - ${plan.name}` : '新增计划路线'}
      onClose={onClose}
      width={860}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button type="submit" form="patrol-plan-form" className="btn btn-primary" disabled={saving}>
            {saving ? '提交中…' : '保存路线'}
          </button>
        </>
      }
    >
      {error ? <div className="alert alert-error">{error}</div> : null}
      <form id="patrol-plan-form" onSubmit={submit} className="form-grid">
        <Field label="路线名称 *">
          <input
            value={form.name}
            onChange={setValue('name')}
            placeholder="如：城东区早班巡查路线"
          />
        </Field>
        <Field label="所属区域 *">
          <input value={form.district} onChange={setValue('district')} placeholder="如：城东区" />
        </Field>
        <Field label="计划巡查人 *">
          <input value={form.inspector} onChange={setValue('inspector')} placeholder="巡查人姓名" />
        </Field>
        <Field label="班次">
          <select value={form.shift} onChange={setValue('shift')}>
            {(dictionaries?.shift || ['早班', '中班', '晚班']).map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>
        <Field label="备注" full>
          <textarea rows="2" value={form.remark} onChange={setValue('remark')} placeholder="选填" />
        </Field>
      </form>

      <div className="card-title">
        <div className="inline">
          <h3>途经点位（按顺序到访）</h3>
          <span className="tag tag-primary">{points.length} 个点位</span>
        </div>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => setPoints((prev) => [...prev, { restroom_id: '', stay_minutes: 15 }])}
        >
          + 添加点位
        </button>
      </div>

      {points.length ? (
        <div className="track-editor">
          <div className="track-row track-row-head plan-point-row">
            <span>顺序</span>
            <span>公厕点位</span>
            <span>计划停留（分钟）</span>
            <span>操作</span>
          </div>
          {points.map((point, index) => (
            <div className="track-row plan-point-row" key={index}>
              <span className="muted">第 {index + 1} 站</span>
              <select
                value={point.restroom_id}
                onChange={(event) => setPoint(index, 'restroom_id', event.target.value)}
              >
                <option value="">请选择公厕</option>
                {options.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.code} {option.name}（{option.district}）
                  </option>
                ))}
              </select>
              <input
                type="number"
                min="1"
                max="240"
                value={point.stay_minutes}
                onChange={(event) => setPoint(index, 'stay_minutes', event.target.value)}
              />
              <span className="inline">
                <button
                  type="button"
                  className="btn-link"
                  title="上移"
                  onClick={() => movePoint(index, -1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="btn-link"
                  title="下移"
                  onClick={() => movePoint(index, 1)}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="btn-link danger"
                  onClick={() => setPoints((prev) => prev.filter((_, idx) => idx !== index))}
                >
                  删除
                </button>
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-block">尚未添加点位，点击「添加点位」按顺序规划路线</div>
      )}
    </Modal>
  );
}
