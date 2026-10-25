/* 匿名设备号：没有账号体系，用浏览器本地 UUID 把记录分开。
   - 存在 localStorage，请求时放在 X-Owner-Id 头里；
   - 清缓存/换浏览器就看不到旧记录，这是这个方案的已知边界（ADR-010）；
   - 它不是身份认证：伪造这个头就能看到别人的记录，demo 场景可接受。 */

const KEY = "cg:owner";

export function ownerId() {
  if (typeof window === "undefined") return "";
  try {
    let id = window.localStorage.getItem(KEY);
    if (!id) {
      id =
        window.crypto && window.crypto.randomUUID
          ? window.crypto.randomUUID()
          : `dev_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
      window.localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    // 隐私模式下 localStorage 可能不可用：退回公共桶，至少不崩
    return "";
  }
}
