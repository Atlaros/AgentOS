"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { LogoutButton } from "./logout-button";
import { ThemeToggle } from "./theme-toggle";

const SIDEBAR_KEY = "agentia.sidebar.hidden";

type IconName =
  | "chat"
  | "orders"
  | "catalog"
  | "cash"
  | "suppliers"
  | "metrics"
  | "knowledge"
  | "customers"
  | "reports"
  | "settings"
  | "ledger"
  | "operator"
  | "more";

type NavItem = { href: string; label: string; icon: IconName; match?: string[] };

const NAV: NavItem[] = [
  { href: "/operator", label: "Operador", icon: "operator" },
  { href: "/", label: "Conversaciones", icon: "chat", match: ["/chats"] },
  { href: "/customers", label: "Clientes", icon: "customers", match: ["/customers"] },
  { href: "/orders", label: "Pedidos", icon: "orders" },
  { href: "/catalog", label: "Inventario", icon: "catalog" },
  { href: "/cash", label: "Caja", icon: "cash" },
  { href: "/ledger", label: "Contabilidad", icon: "ledger" },
  { href: "/suppliers", label: "Proveedores", icon: "suppliers" },
  { href: "/metrics", label: "Analítica", icon: "metrics" },
  { href: "/reports", label: "Reportes", icon: "reports" },
  { href: "/knowledge", label: "Conocimiento", icon: "knowledge" },
  { href: "/settings", label: "Configuración", icon: "settings" },
];

const MOBILE_PRIMARY = 3;

const ICON_PATHS: Record<IconName, string> = {
  chat: "M4 5h16v11H8l-4 4z",
  orders: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6",
  catalog: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  cash: "M3 6h18v12H3zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
  suppliers: "M3 7h11v9H3zM14 10h4l3 3v3h-7zM7 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM17 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
  metrics: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  knowledge: "M5 4h10l4 4v12H5zM15 4v4h4M8 12h8M8 16h6",
  reports: "M6 3h9l3 3v15H6zM9 12h6M9 16h6M9 8h3",
  settings: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 12h2M18 12h2M12 4v2M12 18v2",
  ledger: "M5 4h14v16H5zM8 8h8M8 12h8M8 16h5",
  customers: "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM4 19c0-3 2.2-5 5-5s5 2 5 5M16 11a2.5 2.5 0 1 0 0-5M16 14c2.2 0 4 1.5 4 4",
  operator: "M4 6h16M4 12h10M4 18h7M18 11v6M15 14h6",
  more: "M5 12h.01M12 12h.01M19 12h.01",
};

function Icon({ name }: { name: IconName }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={name === "more" ? 3 : 1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

function isActive(item: NavItem, pathname: string) {
  if (item.href === "/") {
    return pathname === "/" || (item.match ?? []).some((p) => pathname.startsWith(p));
  }
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function NavLink({
  item,
  pathname,
  badge = 0,
}: {
  item: NavItem;
  pathname: string;
  badge?: number;
}) {
  const showBadge = item.href === "/metrics" && badge > 0;
  return (
    <Link
      className="nav-link"
      href={item.href}
      aria-current={isActive(item, pathname) ? "page" : undefined}
    >
      <Icon name={item.icon} />
      <span>{item.label}</span>
      {showBadge ? (
        <span className="nav-badge" aria-label={`${badge} tipos de alerta`}>
          {badge}
        </span>
      ) : null}
    </Link>
  );
}

function Brand({ tenant }: { tenant: string }) {
  return (
    <div className="brand">
      <strong className="brand-mark">
        <span>✦</span> Factory Agent OS
      </strong>
      <span className="brand-tenant">{tenant}</span>
    </div>
  );
}

const MODULE_NAV_HREFS = new Set([
  "/cash",
  "/ledger",
  "/suppliers",
  "/metrics",
  "/reports",
  "/knowledge",
]);

export function AppShell({ tenant, children }: { tenant: string; children: ReactNode }) {
  const pathname = usePathname();
  const [sidebarHidden, setSidebarHidden] = useState(false);
  const [alertTypes, setAlertTypes] = useState(0);
  const [showAnalytics, setShowAnalytics] = useState(true);
  const [moduleNavHrefs, setModuleNavHrefs] = useState<string[] | null>(null);

  useEffect(() => {
    if (pathname === "/login" || pathname === "/owner" || pathname === "/signup") return;
    let cancelled = false;
    fetch("/api/backend/api/shop/modules", { cache: "no-store" })
      .then(async (res) => {
        if (cancelled || !res.ok) return;
        const body = (await res.json()) as { nav_hrefs?: string[] | null };
        setModuleNavHrefs(Array.isArray(body.nav_hrefs) ? body.nav_hrefs : null);
      })
      .catch(() => {
        if (!cancelled) setModuleNavHrefs(null);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  useEffect(() => {
    if (pathname === "/login" || pathname === "/owner" || pathname === "/signup") return;
    if (moduleNavHrefs !== null && !moduleNavHrefs.includes("/metrics")) {
      setShowAnalytics(false);
      setAlertTypes(0);
      return;
    }
    let cancelled = false;
    fetch("/api/backend/api/metrics?period=7d", { cache: "no-store" })
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 403 || res.status === 404) {
          setShowAnalytics(false);
          setAlertTypes(0);
          return;
        }
        if (!res.ok) {
          setAlertTypes(0);
          return;
        }
        setShowAnalytics(true);
        const body = (await res.json()) as { alert_type_count?: number };
        const count = body.alert_type_count;
        setAlertTypes(typeof count === "number" && count > 0 ? count : 0);
      })
      .catch(() => {
        if (!cancelled) setAlertTypes(0);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, moduleNavHrefs]);

  const navItems = NAV.filter((item) => {
    if (item.href === "/metrics" && !showAnalytics) return false;
    if (moduleNavHrefs === null) return true;
    if (!MODULE_NAV_HREFS.has(item.href)) return true;
    return moduleNavHrefs.includes(item.href);
  });

  useEffect(() => {
    try {
      setSidebarHidden(window.localStorage.getItem(SIDEBAR_KEY) === "1");
    } catch {
      setSidebarHidden(false);
    }
  }, []);

  function toggleSidebar() {
    setSidebarHidden((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
      } catch {
        /* ignore quota / private mode */
      }
      return next;
    });
  }

  if (pathname === "/login" || pathname === "/owner" || pathname === "/signup") {
    return <main className="auth">{children}</main>;
  }

  return (
    <div className={sidebarHidden ? "shell shell-sidebar-hidden" : "shell"}>
      <aside className="sidebar" aria-hidden={sidebarHidden}>
        <div className="side-head">
          <Brand tenant={tenant} />
          <button
            type="button"
            className="secondary sidebar-toggle"
            onClick={toggleSidebar}
            aria-expanded={!sidebarHidden}
            aria-controls="app-sidebar-nav"
          >
            Ocultar
          </button>
        </div>
        <nav id="app-sidebar-nav" className="side-nav" aria-label="Secciones">
          {navItems.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} badge={alertTypes} />
          ))}
        </nav>
        <div className="side-foot">
          <ThemeToggle />
          <LogoutButton />
        </div>
      </aside>

      <div className="content">
        <header className="desktop-top">
          {sidebarHidden ? (
            <button
              type="button"
              className="secondary sidebar-show"
              onClick={toggleSidebar}
              aria-expanded={false}
              aria-controls="app-sidebar-nav"
            >
              Menú
            </button>
          ) : null}
        </header>
        <header className="mobile-top">
          <Brand tenant={tenant} />
          <ThemeToggle />
        </header>
        <main className="main">{children}</main>
      </div>

      <nav className="bottom-nav" aria-label="Secciones">
        {navItems.slice(0, MOBILE_PRIMARY).map((item) => (
          <NavLink key={item.href} item={item} pathname={pathname} badge={alertTypes} />
        ))}
        <details className="more" key={pathname}>
          <summary>
            <Icon name="more" />
            <span>Más</span>
          </summary>
          <div className="more-sheet">
            {navItems.slice(MOBILE_PRIMARY).map((item) => (
              <NavLink key={item.href} item={item} pathname={pathname} badge={alertTypes} />
            ))}
            <LogoutButton />
          </div>
        </details>
      </nav>
    </div>
  );
}
