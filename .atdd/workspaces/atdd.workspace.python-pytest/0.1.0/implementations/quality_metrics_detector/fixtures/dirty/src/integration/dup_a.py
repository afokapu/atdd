"""Order total — variant A (copy-pasted body, see dup_b.py)."""


class OrderA:
    def compute(self):
        total = self.base_amount
        total = total + self.tax_amount
        total = total - self.discount
        total = total * self.multiplier
        rounded = round(total, 2)
        return rounded
