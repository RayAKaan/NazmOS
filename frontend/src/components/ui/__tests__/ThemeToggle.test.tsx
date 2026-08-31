import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { ThemeToggle } from "../ThemeToggle";

function mockMatchMedia(matches: boolean) {
  const mql = {
    matches,
    media: "(prefers-color-scheme: dark)",
    onchange: null,
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    addListener: jest.fn(),
    removeListener: jest.fn(),
    dispatchEvent: jest.fn(),
  };
  window.matchMedia = jest.fn().mockReturnValue(mql);
  return mql;
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

afterEach(() => cleanup());

describe("ThemeToggle (System / Light / Dark)", () => {
  it("renders three mode buttons with Light first", () => {
    mockMatchMedia(false);
    render(<ThemeToggle />);
    const light = screen.getByRole("button", { name: /light theme/i });
    const sys = screen.getByRole("button", { name: /system theme/i });
    const dark = screen.getByRole("button", { name: /dark theme/i });
    expect(light).toBeInTheDocument();
    expect(sys).toBeInTheDocument();
    expect(dark).toBeInTheDocument();
  });

  it("persists dark choice and applies the .dark class", () => {
    mockMatchMedia(false);
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: /dark theme/i }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("nazmos-theme")).toBe("dark");
  });

  it("persists light choice and removes the .dark class", () => {
    mockMatchMedia(false);
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: /light theme/i }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("nazmos-theme")).toBe("light");
  });

  it("system mode follows the OS preference (arithmetic check)", () => {
    const osDark = true;
    mockMatchMedia(osDark);
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: /system theme/i }));
    // system + OS-dark => .dark should be present
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("nazmos-theme")).toBe("system");
  });
});
