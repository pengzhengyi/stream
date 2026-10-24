/**
 * @file Mounts the app into the page.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./index.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html must contain an element with id 'root'.");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
