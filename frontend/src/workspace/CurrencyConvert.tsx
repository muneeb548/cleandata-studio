import { useState } from "react";
import { Search } from "lucide-react";
import { api } from "@/api/client";
import type { ColumnProfile } from "@/api/types";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox, FieldHint, Input, Label, Select } from "@/components/ui/form";
import { formatNumber } from "@/lib/utils";
import { CURRENCIES, parseRate, type FormState } from "./operationForms";
import { toApiError } from "./useAsync";

type Props = { form: FormState; set: (patch: Partial<FormState>) => void; cols: ColumnProfile[] };

/** Clean numbers → "Convert all to one currency": choose the target, find the currencies, type the rates. */
export function CurrencyConvert({ form, set, cols }: Props) {
  const [found, setFound] = useState<Record<string, number> | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const turnOn = (on: boolean) => {
    const guess = cols.find((c) => /countr|nation/i.test(c.name) && !form.numColumns.includes(c.name));
    set({ numConvert: on, numCountryColumn: on && !form.numCountryColumn ? (guess?.name ?? "") : form.numCountryColumn });
    setFound(null);
  };

  const findCurrencies = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const res = await api.preview({
        type: "clean_numbers",
        columns: form.numColumns,
        decimal: form.numDecimal,
        on_error: "set_missing",
        country_column: form.numCountryColumn || null,
        default_currency: form.numDefaultCurrency || null,
      });
      const counts = (res.details.currency_counts ?? {}) as Record<string, number>;
      setFound(counts);
      const rates = { ...form.numRates };
      Object.keys(counts).forEach((c) => {
        if (c !== "unknown" && !(c in rates)) rates[c] = "";
      });
      set({ numRates: rates });
    } catch (err) {
      setProblem(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const rateCurrencies = Object.keys(form.numRates).filter((c) => c !== form.numTarget);
  const unknown = found?.unknown ?? 0;

  return (
    <section className="space-y-4 rounded-md border border-border p-4">
      <Checkbox
        id="num-convert"
        checked={form.numConvert}
        onChange={(e) => turnOn(e.target.checked)}
        label="Convert all to one currency"
        description="For a column with $, £, Rs… mixed. You type the exchange rates; nothing is guessed."
      />
      {form.numConvert && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="num-target">Convert to</Label>
              <Select id="num-target" value={form.numTarget} onChange={(e) => set({ numTarget: e.target.value })}>
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="num-country">Country column</Label>
              <Select id="num-country" value={form.numCountryColumn} onChange={(e) => set({ numCountryColumn: e.target.value })}>
                <option value="">None</option>
                {cols
                  .filter((c) => !form.numColumns.includes(c.name))
                  .map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="num-default">Amounts without a mark are in</Label>
              <Select id="num-default" value={form.numDefaultCurrency} onChange={(e) => set({ numDefaultCurrency: e.target.value })}>
                <option value="">Unknown (use the country)</option>
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <FieldHint>
            A clear mark (£, €, USD, PKR) always decides. For plain numbers and for $, Rs and ¥ the row's country is used: Rs in Pakistan is PKR, $ in Canada is CAD.
          </FieldHint>

          <div className="flex flex-wrap items-center gap-3">
            <Button variant="secondary" size="sm" onClick={() => void findCurrencies()} loading={busy} disabled={!form.numColumns.length || busy}>
              {!busy && <Search />} Find currencies in the column
            </Button>
            {!form.numColumns.length && <span className="text-caption text-muted-foreground">Select the amount column below first.</span>}
          </div>
          {problem && <Alert tone="danger" title={problem} />}

          {found && (
            <p className="text-small text-slate-700" aria-live="polite">
              Found:{" "}
              {Object.entries(found)
                .map(([c, n]) => `${c === "unknown" ? "no currency" : c} ${formatNumber(n)}`)
                .join(" · ")}
            </p>
          )}
          {unknown > 0 && (
            <Alert tone="warning" title={`${formatNumber(unknown)} amounts have no currency`}>
              Choose a country column or a default currency above, then find the currencies again.
            </Alert>
          )}

          {rateCurrencies.length > 0 && (
            <fieldset className="space-y-2">
              <legend className="mb-1 text-small font-medium text-slate-700">Exchange rates (ask your client which rate and date to use)</legend>
              {rateCurrencies.map((c) => {
                const text = form.numRates[c] ?? "";
                const bad = text.trim() !== "" && parseRate(text) === null;
                return (
                  <div key={c} className="flex flex-wrap items-center gap-2 text-small">
                    <span className="w-14 font-medium">1 {c} =</span>
                    <Input
                      aria-label={`Rate: 1 ${c} in ${form.numTarget}`}
                      className="w-36"
                      inputMode="decimal"
                      value={text}
                      placeholder="e.g. 0.0036"
                      onChange={(e) => set({ numRates: { ...form.numRates, [c]: e.target.value } })}
                    />
                    <span>{form.numTarget}</span>
                    {bad && <span className="text-caption text-red-700">Not a positive number</span>}
                  </div>
                );
              })}
            </fieldset>
          )}
        </>
      )}
    </section>
  );
}
