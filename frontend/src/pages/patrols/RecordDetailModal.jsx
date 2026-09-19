import DetailList from '../../components/DetailList.jsx';
import Modal from '../../components/Modal.jsx';
import { arrivalRateTone, deviationTone, formatDateTime, formatDuration } from '../../utils/format.js';

export default function RecordDetailModal({ record, onClose }) {
  if (!record) return null;

  return (
    <Modal
      title={`巡查执行详情 - ${record.route_name || '未命名路线'}`}
      onClose={onClose}
      width={760}
      footer={
        <button type="button" className="btn" onClick={onClose}>
          关闭
        </button>
      }
    >
      <DetailList
        items={[
          { label: '巡查路线', value: record.route_name || '-' },
          { label: '巡查人', value: record.inspector },
          { label: '开始时间', value: formatDateTime(record.start_time) },
          { label: '结束时间', value: formatDateTime(record.end_time) },
          { label: '巡查用时', value: formatDuration(record.duration_minutes) },
          {
            label: '到位情况',
            value: (
              <span className="inline">
                <span className={`tag ${arrivalRateTone(record.arrival_rate)}`}>
                  到位率 {record.arrival_rate}%
                </span>
                <span className="muted">
                  {record.arrived_count}/{record.planned_count} 个点位
                </span>
                {record.is_deviated ? <span className="tag tag-danger">偏离明显</span> : null}
              </span>
            ),
          },
          { label: '偏离说明', value: record.deviation_note || '无' },
        ]}
      />

      <div className="section-title">实际巡查轨迹（{record.actual_points.length} 个点位）</div>
      {record.actual_points.length ? (
        <ol className="timeline">
          {record.actual_points.map((point, index) => (
            <li key={index}>
              <div className="head">
                <strong>{point.point_name}</strong>
                {point.planned ? (
                  <span className="tag tag-primary">计划点位</span>
                ) : (
                  <span className="tag tag-info">计划外点位</span>
                )}
                <span className="time">
                  {formatDateTime(point.arrive_at)} ~ {formatDateTime(point.leave_at)}
                </span>
                <span className="muted">停留 {formatDuration(point.stay_minutes)}</span>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className="empty-block">本次巡查无点位打卡记录</div>
      )}

      <div className="section-title">与计划路线比对（{record.deviations.length} 项偏离）</div>
      {record.deviations.length ? (
        <ul className="deviation-list">
          {record.deviations.map((item, index) => (
            <li key={index}>
              <span className={`tag ${deviationTone(item.type)}`}>{item.type}</span>
              {item.point_name ? <strong>{item.point_name}</strong> : null}
              <span className="muted">{item.detail}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty-block">全部按计划执行，无偏离</div>
      )}
    </Modal>
  );
}
