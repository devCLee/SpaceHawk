// The shared 분석 이력 DataTable is the one piece with real logic (client-side
// sort / global filter / pagination over an in-memory dataset) — the tabs are
// fetch wiring. Fixture rows exercise each behavior through the rendered DOM.

import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { type ColumnDef } from "@tanstack/react-table";
import DataTable from "../DataTable";
import { t } from "@/lib/i18n/t";

interface Row {
  name: string;
  score: number;
}

const columns: ColumnDef<Row, unknown>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "score", header: "Score" },
];

const data: Row[] = Array.from({ length: 30 }, (_, i) => ({
  name: `SAT-${String(i).padStart(2, "0")}`,
  score: i,
}));

const firstBodyCell = () => {
  const body = document.querySelector("tbody")!;
  return within(body).getAllByRole("cell")[0];
};

describe("DataTable (client-side)", () => {
  it("renders rows and paginates at pageSize", () => {
    render(
      <DataTable columns={columns} data={data} isLoading={false} pageSize={25} />
    );
    // Page 1 holds 25 of 30 rows.
    expect(screen.getByText("SAT-00")).toBeInTheDocument();
    expect(screen.queryByText("SAT-29")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(t("history.next")));
    expect(screen.getByText("SAT-29")).toBeInTheDocument();
    expect(screen.queryByText("SAT-00")).not.toBeInTheDocument();
  });

  it("sorts on header click (numeric columns toggle desc first)", () => {
    render(<DataTable columns={columns} data={data} isLoading={false} />);
    const header = screen.getByText("Score");
    fireEvent.click(header); // desc (TanStack default for number columns)
    expect(firstBodyCell()).toHaveTextContent("SAT-29");
    fireEvent.click(header); // asc
    expect(firstBodyCell()).toHaveTextContent("SAT-00");
  });

  it("narrows with the global filter", () => {
    render(
      <DataTable
        columns={columns}
        data={data}
        isLoading={false}
        searchPlaceholder="search"
      />
    );
    fireEvent.change(screen.getByPlaceholderText("search"), {
      target: { value: "SAT-07" },
    });
    expect(screen.getByText("SAT-07")).toBeInTheDocument();
    expect(screen.queryByText("SAT-08")).not.toBeInTheDocument();
    expect(screen.getByText(t("history.total", { n: 1 }))).toBeInTheDocument();
  });

  it("shows the empty state and the error state", () => {
    const { unmount } = render(
      <DataTable columns={columns} data={[]} isLoading={false} />
    );
    expect(screen.getByText(t("history.empty"))).toBeInTheDocument();
    unmount();

    render(
      <DataTable columns={columns} data={undefined} isLoading={false} isError />
    );
    expect(screen.getByText(t("history.loadError"))).toBeInTheDocument();
  });
});
