export function createPaymentAttempt(createKey) {
  let product = '', key = '', pending = false
  return {
    begin(productId) {
      if (pending) return null
      if (product !== productId || !key) { product = productId; key = createKey() }
      pending = true
      return key
    },
    finish(completed = false) {
      pending = false
      if (completed) { product = ''; key = '' }
    },
  }
}
