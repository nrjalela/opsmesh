import { useEffect, useState } from "react";

// Hash routing: GitHub Pages serves one static index.html, so #/inbox survives a refresh.

export type RouteMatch =
  | { page: "queue" }
  | { page: "invoice"; id: string }
  | { page: "inbox" }
  | { page: "dashboard" }
  | { page: "controls" };

export function parse(hash: string): RouteMatch {
  const path = hash.replace(/^#/, "") || "/";
  const inv = path.match(/^\/invoice\/([\w-]+)$/);
  if (inv) return { page: "invoice", id: inv[1] };
  if (path === "/inbox") return { page: "inbox" };
  if (path === "/dashboard") return { page: "dashboard" };
  if (path === "/controls") return { page: "controls" };
  return { page: "queue" };
}

export function href(route: RouteMatch): string {
  return route.page === "invoice" ? `#/invoice/${route.id}` : route.page === "queue" ? "#/" : `#/${route.page}`;
}

export function go(route: RouteMatch): void {
  window.location.hash = href(route);
}

export function useRoute(): RouteMatch {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parse(window.location.hash));
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
