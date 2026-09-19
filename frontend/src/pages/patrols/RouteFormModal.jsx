import { useEffect, useMemo, useState } from 'react';

import { metaApi } from '../../api/meta.js';
import { patrolApi } from '../../api/patrols.js';
import Field from '../../components/Field.jsx';
import Modal from '../../components/Modal.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useDictionaries } from '../../hooks/useDictionaries.js';

const EMPTY_POINT = { restroom_id: '', stay_minutes: 10 };

export default function RouteFormModal({ route, onClose, onSaved }) {
  const isEdit = Boolean(route?.id);
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const [options, setOptions] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({
    name: route?.name ?? '',
    district: route?.district ?? '',
    shift: route?.shift ?? '早班',
    enabled: route?.enabled ?? true,
    remark: route?.remark ?? '',
  });
  const [points, setPoints] = useState(
    route?.points?.map((point) => ({
      restroom_id: point.restroom_id,
      stay_minutes: point.stay_minutes,
    })) ?? [{ ...EMPTY_POINT }],
  );

  useEffect(() => {
    metaApi
      .restroomOptions()
      .then(setOptions)
      .catch((err) => setError(err.message));
  }, []);

  const optionName = useMemo(() => {
    const map = new Map(options.map((item) => [item.id, `${item.code} ${item.name}`]));
    return (id) => map.get(Number(id)) || '';
  }, [options]);

  const updatePoint = (index, patch) => {
    setPoints((prev) => prev.map((item, idx) => (idx === index ? { ...item, ...patch } : item)));
  };

  const movePoint = (index, offset) => {
    setPoints((prev) => {
      const next = [...prev];
      const target = index + offset;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const removePoint = (index) => setPoints((prev) => prev.filter((_, idx) => idx !== index));

  const submit = async (event) => {
    event.preventDefault();
    if (!form.name.trim()) {
      setError('请填写路线名称');
      return;
    }
    if (!form.district.trim()) {
      setError('请填写所属区域');
      return;
    }
    const validPoints = points.filter((point) => point.restroom_id);
    if (!validPoints.length) {
      setError('请至少添加一个巡查点位');
      return;
    }
    const ids = validPoints.map((point) => Number(point.restroom_id));
    if (new Set(ids).size !== ids.length) {
      setError('同一公厕在路线中重复，请调整点位');
      return;
    }
    setSaving(true);
    setError(null);
    const payload = {
      ...form,
      name: form.name.trim(),
      district: form.district.trim(),
      remark: form.remark.trim() || null,
      points: validPoints.map((point) => ({
        restroom_id: Number(point.restroom_id),
        stay_minutes: Number(point.stay_minutes) || 1,
      })),
    };
    try {
      if (isEdit) {
        await patrolApi.updateRoute(route.id, payload);
      } else {
        await patrolApi.createRoute(payload);
      }
      toast.success(isEdit ? '路线已更新' : '路线已创建');
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
      title={isEdit ? `编辑路线 - ${route.name}` : '新增巡查路线'}
      onClose={onClose}
      width={760}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button type="submit" form="route-form" className="btn btn-primary" disabled={saving}>
            {saving ? '保存中…' : '保存路线'}
          </button>
        </>
      }
    >
      {error ? <div className="alert alert-error">{error}</div> : null}
      <form id="route-form" onSubmit={submit} className="form-grid">
        <Field label="路线名称 *">
          <input
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
            placeholder="例如：城东区早班巡查线"
          />
        </Field>
        <Field label="所属区域 *">
          <input
            value={form.district}
            onChange={(event) => setForm((prev) => ({ ...prev, district: event.target.value }))}
            placeholder="例如：城东区"
          />
        </Field>
        <Field label="班次">
          <select
            value={form.shift}
            onChange={(event) => setForm((prev) => ({ ...prev, shift: event.target.value }))}
          >
            {(dictionaries?.shift || ['早班', '中班', '晚班']).map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>
        <Field label="状态">
          <select
            value={form.enabled ? '1' : '0'}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, enabled: event.target.value === '1' }))
            }
          >
            <option value="1">启用</option>
            <option value="0">停用</option>
          </select>
        </Field>
      </form>

      <div className="card-title">
        <div className="inline">
          <h3>计划点位（按巡查顺序）</h3>
          <span className="tag tag-primary">{points.filter((p) => p.restroom_id).length} 个点位</span>
        </div>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => setPoints((prev) => [...prev, { ...EMPTY_POINT }])}
        >
          + 添加点位
        </button>
      </div>

      <div className="route-point-list">
        {points.map((point, index) => (
          <div className="route-point-row" key={index}>
            <span className="order">{index + 1}</span>
            <select
              value={point.restroom_id}
              onChange={(event) => updatePoint(index, { restroom_id: event.target.value })}
            >
              <option value="">请选择公厕</option>
              {options.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.code} {option.name}（{option.district}）
                </option>
              ))}
            </select>
            <label className="stay">
              停留
              <input
                type="number"
                min="1"
                max="120"
                value={point.stay_minutes}
                onChange={(event) => updatePoint(index, { stay_minutes: event.target.value })}
              />
              分钟
            </label>
            <div className="inline">
              <button type="button" className="btn-link" onClick={() => movePoint(index, -1)}>
                上移
              </button>
              <button type="button" className="btn-link" onClick={() => movePoint(index, 1)}>
                下移
              </button>
              <button
                type="button"
                className="btn-link danger"
                onClick={() => removePoint(index)}
                disabled={points.length <= 1}
              >
                移除
              </button>
            </div>
          </div>
        ))}
      </div>
      {points.some((point) => point.restroom_id) ? (
        <p className="muted" style={{ fontSize: 12 }}>
          巡查顺序：{points.filter((p) => p.restroom_id).map((p) => optionName(p.restroom_id)).join(' → ')}
        </p>
      ) : null}

      <Field label="备注" full>
        <textarea
          rows="2"
          value={form.remark}
          onChange={(event) => setForm((prev) => ({ ...prev, remark: event.target.value }))}
          placeholder="路线说明，可选"
        />
      </Field>
    </Modal>
  );
}
