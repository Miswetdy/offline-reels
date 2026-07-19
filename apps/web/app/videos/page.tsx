import { VideoList } from "../../components/video-list";

export default function VideosPage() {
  return (
    <main className="mx-auto min-h-screen max-w-3xl p-6">
      <h1 className="text-3xl font-semibold text-slate-950">Videos</h1>
      <p className="mt-2 text-slate-600">Videos are streamed through the Backend API.</p>
      <VideoList />
    </main>
  );
}
