import { JSDOM } from "jsdom";

let parser;

export async function mermaidParser() {
  if (parser) return parser;
  const dom = new JSDOM("<!doctype html><html><body></body></html>", {
    pretendToBeVisual: true,
  });
  for (const name of [
    "window",
    "document",
    "navigator",
    "Element",
    "HTMLElement",
    "SVGElement",
  ]) {
    Object.defineProperty(globalThis, name, {
      value: dom.window[name],
      configurable: true,
    });
  }
  const { default: mermaid } = await import("mermaid");
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    htmlLabels: false,
  });
  parser = mermaid;
  return parser;
}

export async function parseMermaid(source) {
  const mermaid = await mermaidParser();
  const parsed = await mermaid.parse(source, { suppressErrors: false });
  if (!parsed?.diagramType) {
    throw new Error("Mermaid 11.16.0 returned no parsed diagram identity");
  }
  return parsed;
}
