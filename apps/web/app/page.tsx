import { BackendStatus } from "../components/backend-status";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl items-center p-6">
      <section className="w-full rounded-2xl bg-white p-8 shadow-sm ring-1 ring-slate-200">
        <p className="text-sm font-medium tracking-wide text-slate-500">Offline Reels</p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">Production bootstrap</h1>
        <p className="mt-3 text-slate-600">
          This page verifies that the browser can reach the Backend API.
        </p>
        <BackendStatus />
      </section>
    </main>
  );
}
