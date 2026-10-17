import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Cell, ColumnPicker } from "./shared";

describe("Cell", () => {
  it("labels missing values in text", () => {
    render(<Cell value={null} />);
    expect(screen.getByText("missing")).toBeInTheDocument();
  });
});

describe("ColumnPicker", () => {
  it("selects eligible columns and keeps ineligible ones disabled", async () => {
    const onChange = vi.fn();
    render(
      <ColumnPicker
        id="t"
        columns={[
          { name: "age", type: "integer" },
          { name: "city", type: "text" },
        ]}
        selected={[]}
        onChange={onChange}
        disabledReason={(c) => (c.type === "text" ? "Not numeric" : null)}
      />,
    );
    expect(screen.getByLabelText(/city/)).toBeDisabled();
    await userEvent.click(screen.getByText(/Select all eligible/));
    expect(onChange).toHaveBeenCalledWith(["age"]);
  });
});
