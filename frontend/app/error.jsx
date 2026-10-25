"use client";

export default function Error({ error, reset }) {
  return (
    <div className="app">
      <div className="main">
        <div className="entry-wrap">
          <div className="entry">
            <h1>页面出了点问题</h1>
            <p className="sub">
              你的文案没有丢。可以先返回入口重新粘贴，或者点下面的按钮重试。
            </p>
            <div className="form-foot">
              <button className="btn btn-primary" onClick={() => reset()}>
                重试
              </button>
              <a className="btn btn-text btn-sm" href="/">
                回到入口
              </a>
            </div>
            <p className="meta" style={{ marginTop: 20 }}>
              {error?.message || "未知错误"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
