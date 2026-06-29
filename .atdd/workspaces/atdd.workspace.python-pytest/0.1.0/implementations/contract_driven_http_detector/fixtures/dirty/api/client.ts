// Dirty: bypasses the contract-driven HttpClient with a raw fetch() call.
export async function getUser(id: string) {
  const res = await fetch(`/api/users/${id}`);
  return res.json();
}
