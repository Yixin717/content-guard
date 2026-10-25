/* 原型用的假数据 —— 结构与真实 API 对齐：
   /api/check  → violations[] / uncertain[] / suspected[] / human_review / reason
   /api/rewrite → before_violations / after_violations / rounds / changes[] */

const RULE_COUNT = 40;

const SAMPLE_BAD = {
  title: "姐妹们，这条裤子全网最低价！",
  text:
    "姐妹们，这条裤子全网最低价！三天根治大腿根的痘印，国家级品质，加V领福利。" +
    "我自己穿了三个月，洗完不皱，垂感一直在。69 两条，周末截止。",
  violations: [
    {
      n: 1,
      rule_id: "ABS-004",
      rule_title: "禁止价格类绝对化",
      severity: "high",
      quote: "全网最低价",
      source: "《广告绝对化用语执法指南》第二条",
      clause: "包括“国家级”“最高级”“最佳”以及与其含义相同或者近似的其他用语。",
      suggestion: "改为具体、可核对的活动价，例如「这次活动价很划算」",
      confidence: 0.95,
    },
    {
      n: 2,
      rule_id: "FLM-001",
      rule_title: "非医疗商品禁止涉及疾病治疗功能",
      severity: "high",
      quote: "三天根治大腿根的痘印",
      source: "《广告法》第十七条",
      clause:
        "除医疗、药品、医疗器械广告外，禁止其他任何广告涉及疾病治疗功能，并不得使用医疗用语或者易使推销的商品与药品、医疗器械相混淆的用语。",
      suggestion: "降级为主观感受 + 个体差异，例如「我用了两周，痘印看着淡了些，效果因人而异」",
      confidence: 0.96,
    },
    {
      n: 3,
      rule_id: "ABS-001",
      rule_title: "禁止“国家级 / 最高级 / 最佳”类用语",
      severity: "high",
      quote: "国家级品质",
      source: "《广告法》第九条第三项",
      clause: "使用“国家级”、“最高级”、“最佳”等用语。",
      suggestion: "改为可核对的事实描述，例如「做工和走线挺规整」",
      confidence: 0.94,
    },
    {
      n: 4,
      rule_id: "PLT-001",
      rule_title: "禁止站外引流（个人联系方式）",
      severity: "high",
      quote: "加V领福利",
      source: "《小红书社区规范》(2021.12) 3.2.1",
      clause: "发布导流到个人的联系方式，如手机号、微信号、邮箱、地址等。",
      suggestion: "改为平台内互动，例如「想看的姐妹可以在评论区问我」",
      confidence: 0.91,
    },
    {
      n: 5,
      rule_id: "FLM-003",
      rule_title: "禁止虚构使用效果",
      severity: "medium",
      quote: "洗完不皱",
      source: "《广告法》第二十八条第四项",
      clause: "虚构使用商品或者接受服务的效果的。",
      suggestion: "给出可核对的具体次数与主观感受，例如「洗了三次没起皱」",
      confidence: 0.72,
    },
  ],
  rewrite: {
    title: "姐妹们，这条裤子这次活动价很划算！",
    text:
      "姐妹们，这条裤子这次活动价很划算！我用了两周，大腿根的痘印看着淡了些，效果因人而异。" +
      "做工和走线挺规整，我洗了三次没起皱，垂感还在。69 两条，周末截止。想看的姐妹可以在评论区问我。",
    after: 0,
    rounds: 2,
    changes: [
      {
        n: 1,
        before: "全网最低价",
        after: "这次活动价很划算",
        reason: "价格类绝对化，改为可核对的活动描述",
      },
      {
        n: 2,
        before: "三天根治大腿根的痘印",
        after: "我用了两周，大腿根的痘印看着淡了些，效果因人而异",
        reason: "非医疗商品不得宣称治疗功能，降级为主观感受",
      },
      {
        n: 3,
        before: "国家级品质",
        after: "做工和走线挺规整",
        reason: "去掉绝对化用语，换成可核对的事实",
      },
      {
        n: 4,
        before: "加V领福利",
        after: "想看的姐妹可以在评论区问我",
        reason: "站外引流改为平台内互动",
      },
      {
        n: 5,
        before: "洗完不皱",
        after: "洗了三次没起皱",
        reason: "给出具体次数，避免绝对化效果承诺",
      },
    ],
  },
};

const SAMPLE_CLEAN = {
  title: "胯宽姐妹看这条，我穿一周了",
  text:
    "上周在杭州逛小店，随手拿了这条冰丝阔腿裤试，胯那块儿被遮得挺好，走路时裤管往下坠，不贴腿。" +
    "69 两条，我一条放家里一条放办公室。洗过两次，垂感还在。",
  violations: [],
  rewrite: null,
  coverage: {
    rules: RULE_COUNT,
    manual: [
      "商品资质：材质与成分是否与描述相符",
      "账号报备：是否已走品牌合作报备",
      "图片与视频：本次仅检查文本",
    ],
  },
};

const RECENT = [
  { title: "胯宽姐妹看这条，我穿一周了", n: 0, date: "10/25 10:12" },
  { title: "冰丝阔腿裤 · 促销型", n: 3, date: "10/24 17:26" },
  { title: "ZARA 皮夹克探店", n: 1, date: "10/24 15:12" },
];
