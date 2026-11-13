export function pricePayload({ originalPrice, salePrice }) {
  return { originalAmountCents: Math.round(Number(originalPrice) * 100), amountCents: Math.round(Number(salePrice) * 100) }
}

export function discountLabel(originalCents, saleCents) {
  if (originalCents == null || saleCents == null) return '—'
  const original = Number(originalCents), sale = Number(saleCents)
  if (!Number.isFinite(original) || !Number.isFinite(sale) || original < 0 || sale < 0 || sale > original) return '—'
  if (!original || sale === original) return '无折扣'
  const tenths = Math.floor((sale * 200 + original) / (2 * original))
  return `${(tenths / 10).toFixed(1)}折`
}
