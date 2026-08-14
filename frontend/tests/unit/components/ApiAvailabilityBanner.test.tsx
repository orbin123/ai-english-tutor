import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiAvailabilityBanner } from "@/components/ApiAvailabilityBanner";
import { renderWithProviders } from "../../utils/render";

describe("ApiAvailabilityBanner", () => {
  it("stays hidden when the API is live", async () => {
    const checkAvailability = vi.fn().mockResolvedValue("live");

    renderWithProviders(
      <ApiAvailabilityBanner checkAvailability={checkAvailability} />,
    );

    await waitFor(() => expect(checkAvailability).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/demo api is offline/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
  });

  it("shows warming copy and recovers after a successful manual retry", async () => {
    const checkAvailability = vi
      .fn()
      .mockResolvedValueOnce("warming")
      .mockResolvedValueOnce("live");

    renderWithProviders(
      <ApiAvailabilityBanner checkAvailability={checkAvailability} />,
    );

    expect(await screen.findByText("Demo is warming up")).toBeInTheDocument();
    expect(screen.getByText(/starting and checking its database/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() =>
      expect(screen.queryByText("Demo is warming up")).not.toBeInTheDocument(),
    );
  });

  it("shows honest offline copy for an unreachable API", async () => {
    const checkAvailability = vi.fn().mockResolvedValue("offline");

    renderWithProviders(
      <ApiAvailabilityBanner checkAvailability={checkAvailability} />,
    );

    expect(await screen.findByText("Demo API is offline")).toBeInTheDocument();
    expect(screen.getByText(/may be asleep between demo sessions/i)).toBeInTheDocument();
  });

  it("labels an unexpected health error as attention, not sleep", async () => {
    const checkAvailability = vi.fn().mockResolvedValue("error");

    renderWithProviders(
      <ApiAvailabilityBanner checkAvailability={checkAvailability} />,
    );

    expect(await screen.findByText("Demo API needs attention")).toBeInTheDocument();
    expect(screen.getByText(/not classified as a sleeping environment/i)).toBeInTheDocument();
    expect(screen.queryByText("Demo API is offline")).not.toBeInTheDocument();
  });
});
