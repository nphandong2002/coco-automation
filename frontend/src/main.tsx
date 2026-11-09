import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Channels from "./pages/Channels";
import ChannelDetail from "./pages/ChannelDetail";
import Characters from "./pages/Characters";
import CharacterDetail from "./pages/CharacterDetail";
import Settings from "./pages/Settings";
import Assets from "./pages/Assets";
import ContentLibrary from "./pages/ContentLibrary";
import ContentDetail from "./pages/ContentDetail";
import Production from "./pages/Production";
import Publishing from "./pages/Publishing";
import Scheduler from "./pages/Scheduler";
import Analytics from "./pages/Analytics";
import "./index.css";

function NotFound() {
  return <div className="card p-8 text-center">Không tìm thấy trang.</div>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="channels" element={<Channels />} />
          <Route path="channels/:channelId" element={<ChannelDetail />} />
          <Route path="channels/:channelId/characters/:characterId" element={<CharacterDetail />} />
          <Route path="characters" element={<Characters />} />
          <Route path="content" element={<ContentLibrary />} />
          <Route path="channels/:channelId/content/:projectId" element={<ContentDetail />} />
          <Route path="production" element={<Production />} />
          <Route path="publishing" element={<Publishing />} />
          <Route path="scheduler" element={<Scheduler />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="assets" element={<Assets />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
