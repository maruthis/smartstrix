import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button, CheckboxGroup, Field, Select, TextArea, TextInput, Toggle } from "./Form";

describe("Button", () => {
  it("renders each variant without crashing and forwards onClick", async () => {
    const onClick = vi.fn();
    const { rerender } = render(
      <Button variant="primary" onClick={onClick}>
        Go
      </Button>
    );
    await userEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalledTimes(1);

    for (const variant of ["secondary", "danger", "ghost"] as const) {
      rerender(<Button variant={variant}>Go</Button>);
      expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
    }
  });

  it("defaults to the primary variant", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
  });
});

describe("TextInput / TextArea / Select", () => {
  it("TextInput forwards value and onChange", async () => {
    const onChange = vi.fn();
    render(<TextInput value="" onChange={onChange} placeholder="type here" />);
    await userEvent.type(screen.getByPlaceholderText("type here"), "a");
    expect(onChange).toHaveBeenCalled();
  });

  it("TextArea renders and accepts input", async () => {
    const onChange = vi.fn();
    render(<TextArea value="" onChange={onChange} placeholder="notes" />);
    await userEvent.type(screen.getByPlaceholderText("notes"), "x");
    expect(onChange).toHaveBeenCalled();
  });

  it("Select renders options and calls onChange", async () => {
    const onChange = vi.fn();
    render(
      <Select
        value="a"
        onChange={onChange}
        options={[
          { value: "a", label: "Option A" },
          { value: "b", label: "Option B" },
        ]}
      />
    );
    await userEvent.selectOptions(screen.getByRole("combobox"), "Option B");
    expect(onChange).toHaveBeenCalledWith("b");
  });
});

describe("Toggle", () => {
  it("calls onChange with the flipped value when clicked", async () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("renders as checked and can be disabled", async () => {
    const onChange = vi.fn();
    render(<Toggle checked onChange={onChange} disabled />);
    const toggle = screen.getByRole("button");
    expect(toggle).toBeDisabled();
    await userEvent.click(toggle);
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("Field", () => {
  it("renders a label, hint, and children", () => {
    render(
      <Field label="Name" hint="Required">
        <input aria-label="name-input" />
      </Field>
    );
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByLabelText("name-input")).toBeInTheDocument();
  });

  it("renders without a hint", () => {
    render(
      <Field label="Name">
        <input aria-label="name-input" />
      </Field>
    );
    expect(screen.getByText("Name")).toBeInTheDocument();
  });
});

describe("CheckboxGroup", () => {
  const options = [
    { value: "owasp_top_10", label: "OWASP Top 10", description: "Default map" },
    { value: "pci_dss", label: "PCI DSS" },
  ];

  it("toggles options and refuses to drop below minSelected", async () => {
    const onChange = vi.fn();
    render(<CheckboxGroup values={["owasp_top_10"]} onChange={onChange} options={options} minSelected={1} />);

    const owasp = screen.getByRole("checkbox", { name: /OWASP Top 10/ });
    expect(owasp).toBeChecked();
    expect(owasp).toBeDisabled();
    await userEvent.click(owasp);
    expect(onChange).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("checkbox", { name: "PCI DSS" }));
    expect(onChange).toHaveBeenCalledWith(["owasp_top_10", "pci_dss"]);
  });

  it("unchecks a selected option when above minSelected", async () => {
    const onChange = vi.fn();
    render(<CheckboxGroup values={["owasp_top_10", "pci_dss"]} onChange={onChange} options={options} minSelected={1} />);

    await userEvent.click(screen.getByRole("checkbox", { name: /OWASP Top 10/ }));
    expect(onChange).toHaveBeenCalledWith(["pci_dss"]);
  });
});
