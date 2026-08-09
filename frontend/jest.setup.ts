import "@testing-library/jest-dom";

// jsdom lacks URL.createObjectURL used by some UI components.
if (typeof window !== "undefined" && !window.URL.createObjectURL) {
  window.URL.createObjectURL = () => "";
}
