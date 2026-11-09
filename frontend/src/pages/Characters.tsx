import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { CharacterCard, CreateCharacterForm } from "../components/CharacterForms";
import { Empty, ErrorBox, Field, Loading, Modal } from "../components/ui";
import { useAction, useApi } from "../lib/hooks";

export default function Characters() {
  const chars = useApi(api.allCharacters);
  const channels = useApi(api.channels);
  const [filter, setFilter] = useState<string>("all");
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [target, setTarget] = useState<number | null>(null);
  const { busy, run } = useAction();
  const nav = useNavigate();

  const list = useMemo(() => (chars.data ?? []).filter((c) =>
    (filter === "all" || String(c.owner_channel_id) === filter) &&
    (!q || c.name.toLowerCase().includes(q.toLowerCase()) || c.species.toLowerCase().includes(q.toLowerCase()))), [chars.data, filter, q]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="h1">Characters</h1>
        <button className="btn-primary" disabled={!channels.data?.length} onClick={() => { setTarget(channels.data?.[0]?.id ?? null); setCreating(true); }}>+ Tạo nhân vật</button>
      </div>
      <div className="flex flex-wrap gap-3">
        <select className="input w-56" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">Tất cả kênh</option>
          {channels.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input className="input w-64" placeholder="Tìm theo tên, loài…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {chars.loading && !chars.data ? <Loading /> : chars.error ? <ErrorBox error={chars.error} onRetry={chars.reload} /> :
        !list.length ? <Empty title="Không có nhân vật">{channels.data?.length ? "Tạo nhân vật cho một kênh để bắt đầu." : "Hãy tạo kênh trước, sau đó tạo nhân vật cho kênh."}</Empty> :
          <div className="grid gap-4 md:grid-cols-2">{list.map((c) => <CharacterCard key={c.id} c={c} showOwner />)}</div>}

      {creating && target && (
        <Modal title="Tạo nhân vật" wide onClose={() => setCreating(false)}>
          <div className="mb-4"><Field label="Kênh sở hữu">
            <select className="input" value={target} onChange={(e) => setTarget(+e.target.value)}>
              {channels.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select></Field></div>
          <CreateCharacterForm busy={busy} onCancel={() => setCreating(false)} onSubmit={async (v) => {
            const c = await run(() => api.createCharacter(target, v), "Đã tạo nhân vật");
            if (c) nav(`/channels/${target}/characters/${c.id}`);
          }} />
        </Modal>
      )}
    </div>
  );
}
