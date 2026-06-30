"""Invoice total — variant B (copy-pasted body, see dup_a.py)."""


class InvoiceB:
    def compute(self):
        total = self.base_amount
        total = total + self.tax_amount
        total = total - self.discount
        total = total * self.multiplier
        rounded = round(total, 2)
        return rounded
