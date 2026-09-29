import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import type { Batch } from "./types";

const root = createRoot(document.getElementById("root")!);

fetch(`${import.meta.env.BASE_URL}data/batch.json`)
  .then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json() as Promise<Batch>;
  })
  .then((batch) =>
    root.render(
      <StrictMode>
        <App batch={batch} />
      </StrictMode>,
    ),
  )
  .catch((e) => {
    root.render(
      <p className="load-error">
        Couldn't load the recorded runs ({String(e.message ?? e)}). Try refreshing the page.
      </p>,
    );
  });
