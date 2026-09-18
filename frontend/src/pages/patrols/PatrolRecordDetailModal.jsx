import { useEffect, useState } from 'react';

import { patrolPlanApi, patrolRecordApi } from '../../api/patrols.js';
import DetailList from '../../components/DetailList.jsx';
import Modal from '../../components/Modal.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useAsync } from '../../hooks/useAsync.js';
import { formatDateTime } from '../../utils/format.js';
import { deviationTone, formatMinutes } from '../../utils/patrol.js';

export default function PatrolRecordDetailModal({ record, onClose, onSaved }) {
  const toast = useToast();
  const [note, setNote] = useState(record.deviation_note || '');
  const [saving, setSaving] = useState(false);

  // 计划路线点位用于「计划 vs 实际」对比
  const { data: plan } = useAsync(() => patrolPlanApi.detail(record.plan_id), [record.plan_id]);

  useEffect(() => {
    setNote(record.deviation_note || '');
  }, [record.id, record.deviation_note]);

  if (!record) return null;

  const deviation = record.deviation || { missed: [], extra: [], out_of_order: false };
  const hasDeviation = record.deviation_level !== '无偏离';
  const needNote = record.deviation_level === '明显偏离' && !record.deviation_note;

  const trackByRestroom = new Map((record.tracks || []).map((track) => [track.restroom_id, track]));
  const plannedIds = new Set((plan?.points || []).map((point) => point.restroom_id));
  const extraTracks = (record.tracks || []).filter((track) => !plannedIds.has(track.restroom_id));

  const saveNote = async () => {
    if (record.deviation_level === '明显偏离' && !note.trim()) {
      toast.error('本次巡查偏离明显，说明不能为空');
      return;
    }
    setSaving(true);
    try {
      const updated = await patrolRecordApi.update(record.id, {
        deviation_note: note.trim() || null,
      });
      toast.success('偏离说明已保存');
      onSaved(updated);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={`巡查路线记录 - ${record.plan_name}`}
      onClose={onClose}
      width={860}
      footer={
        <button type="button" className="btn" onClick={onClose}>
          关闭
        </button>
      }
    >
      <DetailList
        items={[
          { label: '计划路线', value: record.plan_name },
          { label: '巡查人', value: record.inspector },
          { label: '开始时间', value: formatDateTime(record.start_time) },
          { label: '结束时间', value: formatDateTime(record.end_time) },
          { label: '巡查耗时', value: formatMinutes(record.duration_minutes) },
          { label: '到位率', value: `${record.arrival_rate}%` },
          {
            label: '偏离情况',
            value: (
              <span className={`tag ${deviationTone(record.deviation_level)}`}>
                {record.deviation_level}
              </span>
            ),
          },
          { label: '备注', value: record.remark || '无' },
        ]}
      />

      {hasDeviation ? (
        <div
          className={`alert ${record.deviation_level === '明显偏离' ? 'alert-error' : 'alert-info'}`}
          style={{ marginTop: 12 }}
        >
          {deviation.missed.length ? (
            <div>漏巡点位：{deviation.missed.map((point) => point.restroom_name).join('、')}</div>
          ) : null}
          {deviation.extra.length ? (
            <div>计划外点位：{deviation.extra.map((point) => point.restroom_name).join('、')}</div>
          ) : null}
          {deviation.out_of_order ? <div>到访顺序与计划路线不一致</div> : null}
        </div>
      ) : null}

      <div className="section-title">计划路线与实际轨迹对比</div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>顺序</th>
              <th>点位</th>
              <th>计划停留</th>
              <th>实际到达</th>
              <th>实际离开</th>
              <th>实际停留</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {(plan?.points || []).map((point, index) => {
              const track = trackByRestroom.get(point.restroom_id);
              return (
                <tr key={`planned-${point.restroom_id}`}>
                  <td>第 {index + 1} 站</td>
                  <td>{point.restroom_name}</td>
                  <td>{formatMinutes(point.stay_minutes)}</td>
                  <td>{track ? formatDateTime(track.arrive_time) : '-'}</td>
                  <td>{track ? formatDateTime(track.leave_time) : '-'}</td>
                  <td>{track ? formatMinutes(track.stay_minutes) : '-'}</td>
                  <td>
                    {track ? (
                      <span className="tag tag-success">到位</span>
                    ) : (
                      <span className="tag tag-danger">漏巡</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {extraTracks.map((track) => (
              <tr key={`extra-${track.restroom_id}`}>
                <td>-</td>
                <td>{track.restroom_name}</td>
                <td>-</td>
                <td>{formatDateTime(track.arrive_time)}</td>
                <td>{formatDateTime(track.leave_time)}</td>
                <td>{formatMinutes(track.stay_minutes)}</td>
                <td>
                  <span className="tag tag-warning">计划外</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">偏离说明{record.deviation_level === '明显偏离' ? '（必填）' : ''}</div>
      {needNote ? (
        <div className="alert alert-error">本次巡查与计划路线偏离明显，请补充说明原因。</div>
      ) : null}
      <textarea
        rows="3"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="说明偏离原因与后续处理，如：沿线施工围挡，临时跳过封闭点位，次日补巡"
        style={{ width: '100%' }}
      />
      <div className="inline" style={{ marginTop: 8, justifyContent: 'flex-end' }}>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={saveNote}
          disabled={saving}
        >
          {saving ? '保存中…' : '保存偏离说明'}
        </button>
      </div>
    </Modal>
  );
}
