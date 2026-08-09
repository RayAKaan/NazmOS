import { render, screen } from "@testing-library/react";
import { useAuthStore } from "@/stores/authStore";
import { EMPTY_CAPABILITIES } from "@/lib/auth";
import RouteGuard from "@/components/RouteGuard";

const routerMock = { replace: jest.fn(), push: jest.fn() };

jest.mock("next/navigation", () => ({
  useRouter: () => routerMock,
}));

beforeEach(() => {
  jest.clearAllMocks();
  useAuthStore.setState({
    user: null,
    capabilities: EMPTY_CAPABILITIES,
    isAuthenticated: false,
    isLoading: false,
  });
});

describe("RouteGuard", () => {
  it("redirects unauthenticated visitors away from dashboard routes to /login", () => {
    useAuthStore.setState({ isAuthenticated: false, isLoading: false });
    render(<RouteGuard>protected</RouteGuard>);
    expect(routerMock.replace).toHaveBeenCalledWith("/login");
  });

  it("renders children for authenticated users with the required capability", () => {
    useAuthStore.setState({
      isAuthenticated: true,
      isLoading: false,
      capabilities: { ...EMPTY_CAPABILITIES, can_view_ops_console: true },
    });
    render(<RouteGuard require="can_view_ops_console">ops-content</RouteGuard>);
    expect(screen.getByText("ops-content")).toBeInTheDocument();
    expect(routerMock.replace).not.toHaveBeenCalled();
  });

  it("redirects authenticated non-founders away from /ops to /dashboard", () => {
    useAuthStore.setState({
      isAuthenticated: true,
      isLoading: false,
      capabilities: { ...EMPTY_CAPABILITIES, can_view_ops_console: false, role: "owner" },
    });
    render(<RouteGuard require="can_view_ops_console">ops-content</RouteGuard>);
    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
    expect(screen.queryByText("ops-content")).not.toBeInTheDocument();
  });

  it("redirects users lacking can_manage_team to /dashboard", () => {
    useAuthStore.setState({
      isAuthenticated: true,
      isLoading: false,
      capabilities: { ...EMPTY_CAPABILITIES, can_manage_team: false, role: "staff" },
    });
    render(<RouteGuard require="can_manage_team">team-content</RouteGuard>);
    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
  });
});
