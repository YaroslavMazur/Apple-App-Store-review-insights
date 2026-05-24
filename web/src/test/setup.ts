import "@testing-library/jest-dom/vitest";

// Recharts uses ResizeObserver which jsdom lacks.
class ResizeObserverShim {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverShim as never);
