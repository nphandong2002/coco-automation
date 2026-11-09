import { api } from "../api/client";
import { ErrorBox, Loading, Stat } from "../components/ui";
import { fmtDate, useApi } from "../lib/hooks";

export default function Settings() {
  const info = useApi(api.systemInfo);
  const logs = useApi(() => api.logs(100));
  const i = info.data;
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="h1">System Settings</h1>
        <button className="btn-ghost" onClick={() => { void info.reload(); void logs.reload(); }}>↻ Làm mới</button>
      </div>
      {info.loading && !i ? <Loading /> : info.error ? <ErrorBox error={info.error} onRetry={info.reload} /> : i && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="CPU" value={`${i.cpu_percent.toFixed(0)}%`} />
            <Stat label="RAM" value={`${i.ram_used_percent.toFixed(0)}%`} sub={`Tổng ${i.ram_total_gb} GB`} />
            <Stat label="Ổ đĩa trống" value={`${i.disk_free_gb} GB`} sub={`Tổng ${i.disk_total_gb} GB`} />
            <Stat label="Database" value={i.database_ok ? "OK" : "Lỗi"} sub={i.database_ok ? `Migration ${i.migration_revision ?? "?"}` : i.database_message} />
          </div>
          <div className="card space-y-2 p-5 text-sm">
            <Check ok={i.database_ok} label="Kết nối PostgreSQL" />
            <Check ok={!!i.migration_revision} label={`Schema đã migrate (${i.migration_revision ?? "chưa"})`} />
            <Check ok={i.secret_key_configured} label="SECRET_KEY đã cấu hình (mã hóa OAuth token)" />
            <Check ok={!!i.ffmpeg_path} label={`FFmpeg ${i.ffmpeg_path ?? "chưa cài (cần cho Phase 2)"}`} />
            <Check ok={i.dashboard_auth_enabled} label="Bảo vệ dashboard bằng mật khẩu (DASHBOARD_PASSWORD)" />
            <div className="pt-2 text-ink-500">Thư mục lưu trữ: <code>{i.storage_dir}</code> · Phiên bản {i.app_version}</div>
          </div>
        </>
      )}
      <div className="card">
        <div className="border-b border-brand-50 px-5 py-3 font-semibold">Nhật ký hệ thống</div>
        {logs.error ? <div className="p-5"><ErrorBox error={logs.error} /></div> : (
          <div className="max-h-[480px] divide-y divide-brand-50 overflow-y-auto">
            {logs.data?.map((l) => (
              <div key={l.id} className="grid grid-cols-[150px_70px_1fr] gap-3 px-5 py-2 text-sm">
                <span className="text-xs text-ink-500">{fmtDate(l.created_at)}</span>
                <span className={`text-xs font-semibold uppercase ${l.level === "error" ? "text-red-700" : l.level === "warning" ? "text-amber-700" : "text-ink-500"}`}>{l.category}</span>
                <span>{l.message}{l.channel_name && <span className="text-ink-500"> · {l.channel_name}</span>}</span>
              </div>
            ))}
            {logs.data?.length === 0 && <div className="muted p-5">Chưa có nhật ký.</div>}
          </div>
        )}
      </div>
    </div>
  );
}

const Check = ({ ok, label }: { ok: boolean; label: string }) => (
  <div className="flex items-center gap-2"><span className={ok ? "text-emerald-600" : "text-amber-600"}>{ok ? "✔" : "!"}</span>{label}</div>
);
