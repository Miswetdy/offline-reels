import Link from "next/link";

type AppBottomNavigationProps = {
  activeRoute: "videos" | "offline";
  withReelsGlassBackdrop?: boolean;
};

function HomeDownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 10.5 12 4l8 6.5v8A1.5 1.5 0 0 1 18.5 20h-13A1.5 1.5 0 0 1 4 18.5v-8Z" />
      <path d="M12 9v6m0 0-2.5-2.5M12 15l2.5-2.5M8.5 18h7" />
    </svg>
  );
}

function OfflineLibraryIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="4" y="3.5" width="16" height="17" rx="4" />
      <path d="m10 8.5 5 3.5-5 3.5v-7Z" fill="currentColor" stroke="none" />
      <path d="M7 6.5h.01M7 17.5h.01M17 6.5h.01M17 17.5h.01" strokeWidth="2.5" />
    </svg>
  );
}

export function AppBottomNavigation({ activeRoute, withReelsGlassBackdrop = false }: AppBottomNavigationProps) {
  const isVideosActive = activeRoute === "videos";
  const isOfflineActive = activeRoute === "offline";

  return (
    <>
      {withReelsGlassBackdrop ? <div className="reels-bottom-glass-backdrop" data-testid="reels-bottom-glass-backdrop" aria-hidden="true" /> : null}
      <nav className="app-bottom-navigation app-bottom-navigation--floating" aria-label="Основная навигация" data-testid="app-bottom-navigation">
      <div className="app-bottom-navigation__pill">
        <Link
          className={`app-bottom-navigation__item${isVideosActive ? " app-bottom-navigation__item--active" : ""}`}
          href="/videos"
          aria-label="Главная и загрузка"
          aria-current={isVideosActive ? "page" : undefined}
          data-testid="bottom-navigation-videos"
        >
          <HomeDownloadIcon />
        </Link>
        <Link
          className={`app-bottom-navigation__item${isOfflineActive ? " app-bottom-navigation__item--active" : ""}`}
          href="/offline"
          aria-label="Офлайн-библиотека"
          aria-current={isOfflineActive ? "page" : undefined}
          data-testid="bottom-navigation-offline"
        >
          <OfflineLibraryIcon />
        </Link>
      </div>
      </nav>
    </>
  );
}
