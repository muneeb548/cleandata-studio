import { render, screen } from "@testing-library/react";
import { Alert } from "./alert";

describe("Alert", () => {
  it("announces errors with role=alert and shows text, not just colour", () => {
    render(<Alert tone="danger" title="Upload failed">Check the file.</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Upload failed");
    expect(alert).toHaveTextContent("Check the file.");
  });
});
