import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import ChannelForm, { emptyChannelInput } from "../components/ChannelForm";
import { Empty, ErrorBox, Loading, Modal, StatusBadge } from "../components/ui";
import { useAction, useApi } from "../lib/hooks";

export default function Channels() {
  const { data, error, loading, reload } = useApi(api.channels);
  const [creating, setCreating] = useState(false);
  const { busy, run } = useAction();
  const nav = useNavigate();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="h1">Channels</h1>
        <button className="btn-primary" onClick={() => setCreating(true)}>+ Thêm kênh</button>
      </div>

      {loading && !data ? <Loading /> : error ? <ErrorBox error={error} onRetry={reload} /> : !data?.length ? (
        <Empty title="Chưa có kênh nào">Tạo kênh đầu tiên để bắt đầu: thương hiệu, nhân vật và lịch đăng riêng cho từng kênh.</Empty>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((c) => (
            <Link key={c.id} to={`/channels/${c.id}`} className="card overflow-hidden transition hover:shadow-md">
              <div className="h-24 bg-gradient-to-r from-brand-100 to-brand-50">
                {c.banner_url && <img src={c.banner_url} alt="" className="h-full w-full object-cover" />}
              </div>
              <div className="-mt-8 flex items-end gap-3 px-4">
                <div className="h-16 w-16 overflow-hidden rounded-full border-4 border-white bg-brand-100">
                  {c.avatar_url ? <img src={c.avatar_url} alt="" className="h-full w-full object-cover" /> :
                    <div className="flex h-full items-center justify-center text-xl font-bold text-brand-700">{c.name[0]}</div>}
                </div>
                <div className="pb-1"><StatusBadge status={c.status} /></div>
              </div>
              <div className="space-y-1 p-4 pt-2">
                <div className="font-semibold">{c.name}</div>
                <div className="font-mono text-xs text-ink-500">{c.code} · {c.language.toUpperCase()} · {c.target_country}</div>
                <div className="line-clamp-2 text-sm text-ink-700">{c.description || <span className="text-ink-300">Chưa có mô tả</span>}</div>
                <div className="pt-1 text-xs text-ink-500">{c.character_count} nhân vật · {c.topics.slice(0, 3).join(", ") || "chưa có chủ đề"}</div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {creating && (
        <Modal title="Thêm kênh mới" onClose={() => setCreating(false)} wide>
          <ChannelForm initial={emptyChannelInput()} isCreate busy={busy} onCancel={() => setCreating(false)}
            onSubmit={async (v) => {
              const c = await run(() => api.createChannel(v), "Đã tạo kênh");
              if (c) nav(`/channels/${c.id}`);
            }} />
        </Modal>
      )}
    </div>
  );
}
