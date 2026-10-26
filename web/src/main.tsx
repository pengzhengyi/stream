/**
 * @file Mounts the app into the page.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@picocss/pico/css/pico.jade.min.css";

import { App } from "./App";
import "./index.css";
import { applyTheme, savedTheme } from "./theme";

// Before the first render, so a forced theme never flashes the system's.
applyTheme(savedTheme());

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html must contain an element with id 'root'.");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
