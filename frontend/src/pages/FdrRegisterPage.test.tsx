import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const { apiMocks, authState } = vi.hoisted(() => ({
  apiMocks: {
    instruments: vi.fn(),
    institutions: vi.fn(),
    createInstrument: vi.fn(),
  },
  authState: {
    user: {
      role: "scrutiny_officer",
      full_name: "Synthetic Reviewer",
      institution_id: null,
    },
  },
}));

vi.mock("../auth/AuthProvider", () => ({ useAuth: () => authState }));

vi.mock("../lib/api", () => ({
  api: apiMocks,
  ApiError: class ApiError extends Error {},
}));

import { FdrRegisterPage } from "./FdrRegisterPage";

const institutionsPage = {
  items: [
    {
      id: "institution-1",
      code: "SYN-01",
      name: "Synthetic Institute One",
      address: null,
      active: true,
      data_origin: "synthetic_demo",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
  total: 1,
  limit: 100,
  offset: 0,
};

const registerPage = {
  items: [
    {
      id: "fdr-1",
      institution_id: "institution-1",
      obligation_id: null,
      submitted_by_user_id: null,
      supersedes_instrument_id: null,
      successor_instrument_id: null,
      replacement_type: null,
      issuer_name: "Synthetic Bank B",
      beneficiary: null,
      reference_original: "SYN-FDR-B",
      reference_normalized: "SYNFDRB",
      amount: "2000.00",
      issue_date: "2026-01-02",
      maturity_date: "2027-01-02",
      lifecycle_status: "submitted",
      verification_status: "pending_review",
      priority: "high",
      data_origin: "synthetic_demo",
      notes: null,
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-03T00:00:00Z",
    },
    {
      id: "fdr-2",
      institution_id: "institution-1",
      obligation_id: null,
      submitted_by_user_id: null,
      supersedes_instrument_id: null,
      successor_instrument_id: null,
      replacement_type: null,
      issuer_name: "Synthetic Bank A",
      beneficiary: null,
      reference_original: "SYN-FDR-A",
      reference_normalized: "SYNFDRA",
      amount: "1000.00",
      issue_date: "2026-01-01",
      maturity_date: "2027-01-01",
      lifecycle_status: "approved",
      verification_status: "discrepancy_flagged",
      priority: "urgent",
      data_origin: "synthetic_demo",
      notes: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-04T00:00:00Z",
    },
  ],
  total: 2,
  limit: 25,
  offset: 0,
};

describe("FDR register", () => {
  beforeEach(() => {
    authState.user = {
      role: "scrutiny_officer",
      full_name: "Synthetic Reviewer",
      institution_id: null,
    };

    apiMocks.instruments.mockReset().mockResolvedValue(registerPage);
    apiMocks.institutions.mockReset().mockResolvedValue(institutionsPage);
    apiMocks.createInstrument.mockReset();
  });

  it("renders the registry fields as distinct statuses and links each record to its real detail route", async () => {
    render(
      <MemoryRouter>
        <FdrRegisterPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("columnheader", {
        name: /issuing bank/i,
      }),
    ).toBeInTheDocument();

    for (const heading of [
      "Instrument reference",
      "Institution",
      "Amount",
      "Issue date",
      "Maturity date",
      "Lifecycle",
      "Verification",
      "Priority",
    ]) {
      expect(
        screen.getByRole("columnheader", {
          name: new RegExp(heading, "i"),
        }),
      ).toBeInTheDocument();
    }

    expect(
      await screen.findByRole("link", { name: "SYN-FDR-A" }),
    ).toHaveAttribute("href", "/fdrs/fdr-2");

    const institutionLinks = screen.getAllByRole("link", {
      name: "Synthetic Institute One",
    });

    expect(institutionLinks).toHaveLength(2);

    institutionLinks.forEach((link) => {
      expect(link).toHaveAttribute("href", "/institutions/institution-1");
    });

    const lifecycleStatus = document.querySelector(
      '[data-status-category="lifecycle"]',
    );
    expect(lifecycleStatus).toHaveTextContent("Submitted");

    const verificationStatus = document.querySelector(
      '[data-status-category="verification"]',
    );
    expect(verificationStatus).toHaveTextContent("Pending Review");

    const priorityStatus = document.querySelector(
      '[data-status-category="priority"]',
    );
    expect(priorityStatus).toHaveTextContent("High");
  });

  it("sorts only the returned page and sends supported search filters to the API", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <FdrRegisterPage />
      </MemoryRouter>,
    );

    const table = await screen.findByRole("region", {
      name: "FDR register results",
    });

    const amountSortButtons = within(table).getAllByRole("button", {
      name: /^amount/i,
    });

    await user.click(amountSortButtons[0]);

    const tableRows = within(table).getAllByRole("row");

    expect(
      within(tableRows[1]).getByRole("link", {
        name: "SYN-FDR-A",
      }),
    ).toBeInTheDocument();

    const searchInputs = screen.getAllByRole("textbox", {
      name: "Search reference or issuing bank",
    });

    const search = searchInputs[0];

    await user.type(search, "SYN-FDR");

    const applyButtons = screen.getAllByRole("button", {
      name: /apply/i,
    });

    await user.click(applyButtons[0]);

    expect(apiMocks.instruments).toHaveBeenLastCalledWith(
      expect.objectContaining({
        search: "SYN-FDR",
        limit: 25,
        offset: 0,
      }),
    );
  });
});
