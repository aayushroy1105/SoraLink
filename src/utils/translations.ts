import { Language, RequestCategory, RequestStatus, Priority } from "../types"

export interface Translations {
  appName: string
  tagline: string
  subTagline: string
  heading: string
  subheading: string
  supportingText: string
  speakButton: string
  speakSubtext: string
  typedButton: string
  typedSubtext: string
  activeRequestsHeading: string
  noActiveRequests: string
  noActiveRequestsSub: string
  offlineNotice: string
  categories: Record<RequestCategory, {
    label: string
    subLabel: string
    description: string
    shortBadge: string
  }>
  statuses: Record<RequestStatus, {
    title: string
    desc: string
  }>
  priorities: Record<Priority, string>
  voice: {
    title: string
    tapToSpeak: string
    listening: string
    unsupported: string
    transcriptLabel: string
    transcriptPlaceholder: string
    suggestedIntent: string
    confidence: string
    attributes: string
    alternatives: string
    confirmSend: string
    submitting: string
    outcomeSuggested: string
    outcomeRequiresChoice: string
    outcomeUnreliable: string
    errorCapture: string
    emptyPrompt: string
  }
  passengerLogin: {
    title: string
    subtitle: string
    seatLabel: string
    seatPlaceholder: string
    inviteCode: string
    invitePlaceholder: string
    enterButton: string
    loggingIn: string
    seatError: string
    codeError: string
  }
  crew: {
    dashboardTitle: string
    dashboardSubtitle: string
    urgentBadge: string
    routineBadge: string
    queueSummary: string
    emptyQueue: string
    emptyQueueSub: string
    actionAcknowledge: string
    actionAcknowledged: string
    actionSendReply: string
    actionComplete: string
    actionCompleted: string
    paTitle: string
    paSelectCard: string
    paDuration: string
    paBroadcastAction: string
    paActiveNotice: string
    paEndAction: string
    loginTitle: string
    loginSubtitle: string
    pinLabel: string
    pinPlaceholder: string
    loginButton: string
    pinError: string
    filterAll: string
    filterPending: string
    filterAcknowledged: string
    filterCompleted: string
  }
  replyModal: {
    title: string
    selectReply: string
    sendButton: string
    cancelButton: string
  }
  actions: {
    cancel: string
    confirm: string
    close: string
    sendRequest: string
    viewDetails: string
    hearReply: string
    logout: string
  }
}

export const translations: Record<Language, Translations> = {
  en: {
    appName: "SoraLink",
    tagline: "In-Flight Passenger Assistance",
    subTagline: "Direct Cabin Care Link",
    heading: "How may we assist you?",
    subheading: "Thoughtful cabin care at your seat",
    supportingText:
      "Choose a service item below or use voice to speak with cabin attendants.",
    speakButton: "Speak your request",
    speakSubtext: "Touch & speak naturally",
    typedButton: "Type a request",
    typedSubtext: "Choose from approved categories",
    activeRequestsHeading: "Active In-Flight Requests",
    noActiveRequests: "No active requests in queue",
    noActiveRequestsSub:
      "Tap any request card above or touch the microphone to request assistance.",
    offlineNotice:
      "Device is currently offline. Please reconnect to cabin Wi-Fi.",
    categories: {
      water_request: {
        label: "Water",
        subLabel: "お水",
        description: "Fresh drinking water (cold, room temperature, or warm).",
        shortBadge: "Beverage",
      },
      blanket_request: {
        label: "Blanket",
        subLabel: "毛布",
        description: "Freshly laundered cabin blanket for your comfort.",
        shortBadge: "Comfort",
      },
      pillow_request: {
        label: "Pillow",
        subLabel: "枕",
        description: "Supportive in-flight rest pillow.",
        shortBadge: "Rest",
      },
      accessibility_assist: {
        label: "Accessibility assistance",
        subLabel: "お手伝い",
        description: "Urgent mobility, seating, or accessibility support.",
        shortBadge: "Care Priority",
      },
    },
    statuses: {
      PENDING: {
        title: "Pending Crew Review",
        desc: "Request placed and awaiting cabin crew review.",
      },
      ACKNOWLEDGED: {
        title: "Crew Assigned",
        desc: "A cabin attendant has acknowledged your request and is preparing it.",
      },
      COMPLETED: {
        title: "Completed",
        desc: "This cabin service request has been fulfilled.",
      },
      CANCELLED: {
        title: "Cancelled",
        desc: "This request was cancelled by passenger.",
      },
    },
    priorities: {
      URGENT: "Urgent",
      ROUTINE: "Routine",
    },
    voice: {
      title: "Voice Transcript Review",
      tapToSpeak: "Tap microphone to speak",
      listening: "Listening to your request...",
      unsupported:
        "Speech recognition is not supported in this browser. You can type your request below.",
      transcriptLabel: "What we heard (editable)",
      transcriptPlaceholder:
        "Speak using the microphone or type your request here...",
      suggestedIntent: "Suggested Intent",
      confidence: "Confidence Score",
      attributes: "Attributes / Preferences",
      alternatives: "Approved Alternative Intents",
      confirmSend: "Confirm & Send to Crew",
      submitting: "Submitting to Crew...",
      outcomeSuggested: "Recognized with high confidence",
      outcomeRequiresChoice:
        "Multiple interpretations possible — please select",
      outcomeUnreliable: "Low confidence — please verify carefully",
      errorCapture:
        "Could not capture speech. Please try speaking clearly or enter text manually.",
      emptyPrompt: "Tap the microphone to speak, or type your request above.",
    },
    passengerLogin: {
      title: "Passenger Welcome",
      subtitle: "Connect your seat to the cabin crew system",
      seatLabel: "Seat Number",
      seatPlaceholder: "e.g. 18A, 24K",
      inviteCode: "Flight Invite Code",
      invitePlaceholder: "Enter invite code",
      enterButton: "Connect to Flight Cabin",
      loggingIn: "Authenticating seat...",
      seatError: "Please enter a valid seat number (e.g. 18A).",
      codeError: "Please enter an invite code.",
    },
    crew: {
      dashboardTitle: "Cabin Attendant Queue",
      dashboardSubtitle: "Authorized In-Flight Service Station",
      urgentBadge: "Urgent Priority",
      routineBadge: "Routine",
      queueSummary: "Current Cabin Queue",
      emptyQueue: "Queue is Clear",
      emptyQueueSub: "All passenger requests have been fulfilled.",
      actionAcknowledge: "Acknowledge",
      actionAcknowledged: "Acknowledged",
      actionSendReply: "Send Predefined Reply",
      actionComplete: "Complete Request",
      actionCompleted: "Completed",
      paTitle: "Cabin Public Announcement (PA)",
      paSelectCard: "Select Approved Announcement Card",
      paDuration: "Broadcast Duration",
      paBroadcastAction: "Broadcast to Cabin",
      paActiveNotice: "Active Cabin Announcement",
      paEndAction: "End Announcement",
      loginTitle: "Crew Access Portal",
      loginSubtitle: "Sign in with your flight crew security PIN",
      pinLabel: "Crew Security PIN",
      pinPlaceholder: "Enter PIN",
      loginButton: "Access Crew Dashboard",
      pinError: "Invalid PIN. Please check your crew credentials.",
      filterAll: "All",
      filterPending: "Pending",
      filterAcknowledged: "Acknowledged",
      filterCompleted: "Completed",
    },
    replyModal: {
      title: "Select Predefined Crew Response",
      selectReply:
        "Choose from approved response catalog (no arbitrary text permitted):",
      sendButton: "Send Reply to Passenger",
      cancelButton: "Cancel",
    },
    actions: {
      cancel: "Cancel Request",
      confirm: "Confirm & Send",
      close: "Close",
      sendRequest: "Send Request",
      viewDetails: "Details",
      hearReply: "Tap to hear reply",
      logout: "Log out",
    },
  },
  ja: {
    appName: "SoraLink",
    tagline: "機内客室乗務員アシスタント",
    subTagline: "空の架け橋 • おもてなし",
    heading: "ご用件をお伺いいたします",
    subheading: "お席にいながら、いつでも乗務員へお声がけいただけます",
    supportingText:
      "必要な備品をお選びいただくか、音声で自然にお申し付けください。",
    speakButton: "音声でリクエスト",
    speakSubtext: "タップして自然にお話しください",
    typedButton: "文字で入力する",
    typedSubtext: "公認カテゴリーから選択します",
    activeRequestsHeading: "現在進行中のリクエスト",
    noActiveRequests: "進行中のリクエストはありません",
    noActiveRequestsSub:
      "備品カードをタップするか、音声ボタンからお気軽にお申し付けください。",
    offlineNotice: "端末がオフラインです。機内Wi-Fiへ接続してください。",
    categories: {
      water_request: {
        label: "お水",
        subLabel: "Water",
        description: "新鮮な飲用水（冷水・常温・白湯）をご用意します。",
        shortBadge: "お飲み物",
      },
      blanket_request: {
        label: "毛布",
        subLabel: "Blanket",
        description: "清潔な機内用ブランケットをお届けします。",
        shortBadge: "快適品",
      },
      pillow_request: {
        label: "枕",
        subLabel: "Pillow",
        description: "休息をサポートするお座席用枕です。",
        shortBadge: "安眠",
      },
      accessibility_assist: {
        label: "お手伝い・移動サポート",
        subLabel: "Accessibility",
        description: "移動やお座席での介助など優先サポートです。",
        shortBadge: "優先対応",
      },
    },
    statuses: {
      PENDING: {
        title: "乗務員確認待ち",
        desc: "リクエストを送信しました。客室乗務員の確認をお待ちください。",
      },
      ACKNOWLEDGED: {
        title: "担当乗務員受付済",
        desc: "客室乗務員がお席のリクエストを確認し、準備を進めております。",
      },
      COMPLETED: {
        title: "お届け完了",
        desc: "ご用命の対応が完了いたしました。",
      },
      CANCELLED: {
        title: "取り消し済み",
        desc: "お客様によってリクエストが取り消されました。",
      },
    },
    priorities: {
      URGENT: "緊急・優先",
      ROUTINE: "通常",
    },
    voice: {
      title: "音声認識の確認",
      tapToSpeak: "マイクをタップしてお話しください",
      listening: "ご用件を聞き取っています...",
      unsupported:
        "お使いのブラウザは音声認識に対応していません。文字でご入力いただけます。",
      transcriptLabel: "認識結果（タップして編集できます）",
      transcriptPlaceholder:
        "マイクでお話しいただくか、こちらに入力してください...",
      suggestedIntent: "判定されたリクエスト",
      confidence: "認識信頼度スコア",
      attributes: "ご希望条件・指定",
      alternatives: "その他の候補項目",
      confirmSend: "確認して乗務員へ送信",
      submitting: "送信中...",
      outcomeSuggested: "高い精度で判定されました",
      outcomeRequiresChoice: "複数の候補が考えられます。項目をお選びください",
      outcomeUnreliable: "認識が不安定です。内容をご確認ください",
      errorCapture:
        "音声を認識できませんでした。静かな環境でもう一度お話しいただくか、手入力してください。",
      emptyPrompt:
        "マイクをタップしてお話しいただくか、テキストを入力してください。",
    },
    passengerLogin: {
      title: "ご搭乗案内",
      subtitle: "お座席を客室乗務員システムに接続します",
      seatLabel: "座席番号",
      seatPlaceholder: "例: 18A, 24K",
      inviteCode: "便名・招待コード",
      invitePlaceholder: "招待コードを入力",
      enterButton: "機内サービスを開始する",
      loggingIn: "お座席を認証中...",
      seatError: "正しい座席番号を入力してください（例: 18A）。",
      codeError: "招待コードを入力してください。",
    },
    crew: {
      dashboardTitle: "客室乗務員 業務キュー",
      dashboardSubtitle: "機内サービス・リクエスト管理",
      urgentBadge: "緊急・優先対応",
      routineBadge: "通常対応",
      queueSummary: "対応待ちリクエスト一覧",
      emptyQueue: "対応待ちリクエストはありません",
      emptyQueueSub: "すべてのお客様のリクエストに対応が完了しました。",
      actionAcknowledge: "受付する",
      actionAcknowledged: "受付済み",
      actionSendReply: "定型応答を送信",
      actionComplete: "完了にする",
      actionCompleted: "完了済み",
      paTitle: "機内一斉アナウンス (PA)",
      paSelectCard: "事前承認アナウンス項目を選択",
      paDuration: "表示継続時間",
      paBroadcastAction: "客室へ一斉送信",
      paActiveNotice: "現在放送中のアナウンス",
      paEndAction: "放送を終了する",
      loginTitle: "客室乗務員 ログイン",
      loginSubtitle: "専用PINコードを入力してください",
      pinLabel: "乗務員セキュリティPIN",
      pinPlaceholder: "PINを入力",
      loginButton: "ダッシュボードを開く",
      pinError: "PINコードが正しくありません。",
      filterAll: "すべて",
      filterPending: "未受付",
      filterAcknowledged: "受付済",
      filterCompleted: "完了済",
    },
    replyModal: {
      title: "乗務員定型メッセージの選択",
      selectReply:
        "承認済みのメッセージをお選びください（自由入力は禁止されています）:",
      sendButton: "お客様へ送信",
      cancelButton: "キャンセル",
    },
    actions: {
      cancel: "リクエストを取り消す",
      confirm: "確認して送信",
      close: "閉じる",
      sendRequest: "客室乗務員に送信する",
      viewDetails: "詳細を表示",
      hearReply: "タップして音声で聞く",
      logout: "ログアウト",
    },
  },
  zh: {
    appName: "SoraLink",
    tagline: "機內客艙服務助理",
    subTagline: "空中的暖心連結",
    heading: "請問需要甚麼協助？",
    subheading: "輕觸螢幕，即刻為您聯繫客艙機組人員",
    supportingText: "請點選下方服務備品，或透過語音直接向空服員提出需求。",
    speakButton: "語音提出請求",
    speakSubtext: "輕觸並自然對話",
    typedButton: "文字輸入",
    typedSubtext: "從認可的類別中挑選",
    activeRequestsHeading: "當前機內請求",
    noActiveRequests: "目前無進行中的請求",
    noActiveRequestsSub: "請點選上方備品卡片，或使用語音按鈕提出需求。",
    offlineNotice: "裝置目前處於離線狀態，請重新連線至機上Wi-Fi。",
    categories: {
      water_request: {
        label: "飲用水",
        subLabel: "お水",
        description: "純淨飲用水（冷水、常溫或溫熱）。",
        shortBadge: "飲品",
      },
      blanket_request: {
        label: "毛毯",
        subLabel: "毛布",
        description: "潔淨舒適客艙毛毯。",
        shortBadge: "舒適品",
      },
      pillow_request: {
        label: "枕頭",
        subLabel: "枕",
        description: "舒適休息之客艙靠枕。",
        shortBadge: "安歇",
      },
      accessibility_assist: {
        label: "行動與無障礙協助",
        subLabel: "お手伝い",
        description: "行動支援、移動或優先照護需求。",
        shortBadge: "優先照護",
      },
    },
    statuses: {
      PENDING: {
        title: "空服員確認中",
        desc: "請求已送出，等待客艙乘務員確認。",
      },
      ACKNOWLEDGED: {
        title: "空服員已受理",
        desc: "空服人員已確認您的請求並正在準備中。",
      },
      COMPLETED: {
        title: "服務已完成",
        desc: "此項機內服務需求已順利送達處理完畢。",
      },
      CANCELLED: {
        title: "已取消",
        desc: "乘客已取消此項請求。",
      },
    },
    priorities: {
      URGENT: "緊急優先",
      ROUTINE: "一般",
    },
    voice: {
      title: "語音辨識確認",
      tapToSpeak: "點擊麥克風開始說話",
      listening: "正在聆聽您的需求...",
      unsupported: "您的瀏覽器不支援語音輸入功能，可直接以文字輸入。",
      transcriptLabel: "辨識內容（點擊可修改）",
      transcriptPlaceholder: "請使用麥克風說話，或在此輸入您的需求...",
      suggestedIntent: "系統辨識項目",
      confidence: "辨識信心指數",
      attributes: "偏好與規格選項",
      alternatives: "其他可選之服務項目",
      confirmSend: "確認並發送給空服員",
      submitting: "正在送出...",
      outcomeSuggested: "高信心度辨識結果",
      outcomeRequiresChoice: "系統提供多種可能，請選擇正確項目",
      outcomeUnreliable: "辨識訊號較弱，請再次核對",
      errorCapture: "無法清晰擷取語音，請於安靜環境再試一次，或直接輸入文字。",
      emptyPrompt: "點擊麥克風開始說話，或於上方輸入需求。",
    },
    passengerLogin: {
      title: "乘客登入",
      subtitle: "將您的座位連線至機艙服務系統",
      seatLabel: "座位號碼",
      seatPlaceholder: "例如: 18A, 24K",
      inviteCode: "班機邀請代碼",
      invitePlaceholder: "請輸入邀請代碼",
      enterButton: "進入機內服務",
      loggingIn: "正在驗證座位...",
      seatError: "請輸入有效的座位號碼（如 18A）。",
      codeError: "請輸入邀請代碼。",
    },
    crew: {
      dashboardTitle: "客艙空服員工作台",
      dashboardSubtitle: "機內旅客服務專區",
      urgentBadge: "緊急優先",
      routineBadge: "一般處理",
      queueSummary: "等待處理清單",
      emptyQueue: "目前無待辦請求",
      emptyQueueSub: "所有乘客需求皆已處理完畢。",
      actionAcknowledge: "受理需求",
      actionAcknowledged: "已受理",
      actionSendReply: "傳送預設回覆",
      actionComplete: "標記完成",
      actionCompleted: "已完成",
      paTitle: "客艙全體廣播 (PA)",
      paSelectCard: "選擇經審核之廣播卡片",
      paDuration: "廣播持續時間",
      paBroadcastAction: "向客艙發送廣播",
      paActiveNotice: "目前客艙廣播進行中",
      paEndAction: "結束此廣播",
      loginTitle: "機組人員登入",
      loginSubtitle: "請輸入專用安全 PIN 碼",
      pinLabel: "機組人員安全 PIN 碼",
      pinPlaceholder: "請輸入 PIN",
      loginButton: "進入工作台",
      pinError: "PIN 碼不正確。",
      filterAll: "全部",
      filterPending: "待受理",
      filterAcknowledged: "已受理",
      filterCompleted: "已完成",
    },
    replyModal: {
      title: "選擇空服員回覆訊息",
      selectReply: "請由核可的預設訊息中挑選（不開放自由輸入文本）：",
      sendButton: "發送回覆給乘客",
      cancelButton: "取消",
    },
    actions: {
      cancel: "取消請求",
      confirm: "確認並發送",
      close: "關閉",
      sendRequest: "發送給機組人員",
      viewDetails: "查看詳情",
      hearReply: "點擊播放語音",
      logout: "登出",
    },
  },
  hi: {
    appName: "SoraLink",
    tagline: "उड़ान में यात्री सेवा",
    subTagline: "केबिन क्रू डायरेक्ट लिंक",
    heading: "हम आपकी क्या सहायता कर सकते हैं?",
    subheading: "आपकी सीट पर विचारशील केबिन सेवा",
    supportingText:
      "कृपया नीचे दी गई सेवा चुनें या केबिन क्रू से बात करने के लिए आवाज़ का उपयोग करें।",
    speakButton: "बोलकर अनुरोध करें",
    speakSubtext: "स्पर्श करें और स्वाभाविकता से बोलें",
    typedButton: "टाइप करके अनुरोध करें",
    typedSubtext: "स्वीकृत श्रेणियों में से चुनें",
    activeRequestsHeading: "सक्रिय उड़ान अनुरोध",
    noActiveRequests: "फ़िलहाल कोई सक्रिय अनुरोध नहीं है",
    noActiveRequestsSub:
      "सहायता प्राप्त करने के लिए ऊपर दिए गए किसी कार्ड पर टैप करें या माइक्रोफ़ोन छुएं।",
    offlineNotice: "डिवाइस ऑफ़लाइन है। कृपया केबिन वाई-फ़ाई से पुनः कनेक्ट करें।",
    categories: {
      water_request: {
        label: "पीने का पानी",
        subLabel: "Water",
        description: "ताज़ा पीने का पानी (ठंडा, सामान्य या गुनगुना)।",
        shortBadge: "पेय",
      },
      blanket_request: {
        label: "कंबल",
        subLabel: "Blanket",
        description: "आपकी सुविधा के लिए स्वच्छ केबिन कंबल।",
        shortBadge: "आराम",
      },
      pillow_request: {
        label: "तकिया",
        subLabel: "Pillow",
        description: "उड़ान में आराम के लिए आरामदायक तकिया।",
        shortBadge: "विश्राम",
      },
      accessibility_assist: {
        label: "सुलभता सहायता",
        subLabel: "Accessibility",
        description: "गतिशीलता, बैठने या विशेष सहायता के लिए प्राथमिकता सेवा।",
        shortBadge: "प्राथमिकता",
      },
    },
    statuses: {
      PENDING: {
        title: "क्रू समीक्षा प्रतीक्षारत",
        desc: "अनुरोध दर्ज किया गया है, केबिन क्रू की पुष्टि की प्रतीक्षा है।",
      },
      ACKNOWLEDGED: {
        title: "क्रू सदस्य नियुक्त",
        desc: "केबिन क्रू ने आपका अनुरोध स्वीकार कर लिया है और तैयारी कर रहे हैं।",
      },
      COMPLETED: {
        title: "अनुरोध पूर्ण",
        desc: "यह केबिन सेवा सफलतापूर्वक पूरी हो गई है।",
      },
      CANCELLED: {
        title: "रद्द किया गया",
        desc: "यह अनुरोध यात्री द्वारा रद्द कर दिया गया है।",
      },
    },
    priorities: {
      URGENT: "अत्यावश्यक",
      ROUTINE: "सामान्य",
    },
    voice: {
      title: "ध्वनि प्रतिलेख समीक्षा",
      tapToSpeak: "बोलने के लिए माइक दबाएं",
      listening: "आपका अनुरोध सुना जा रहा है...",
      unsupported: "इस ब्राउज़र में ध्वनि पहचान समर्थित नहीं है। आप नीचे टाइप कर सकते हैं।",
      transcriptLabel: "हमने जो सुना (संपादन योग्य)",
      transcriptPlaceholder: "माइक से बोलें या अपना अनुरोध यहां टाइप करें...",
      suggestedIntent: "सुझाया गया अनुरोध",
      confidence: "सटीकता स्कोर",
      attributes: "विकल्प और प्राथमिकताएं",
      alternatives: "स्वीकृत वैकल्पिक अनुरोध",
      confirmSend: "पुष्टि करें और क्रू को भेजें",
      submitting: "भेजा जा रहा है...",
      outcomeSuggested: "उच्च सटीकता से पहचाना गया",
      outcomeRequiresChoice: "एकाधिक विकल्प संभव — कृपया चयन करें",
      outcomeUnreliable: "कम सटीकता — कृपया ध्यान से जांचें",
      errorCapture: "ध्वनि स्पष्ट नहीं सुनी जा सकी। कृपया पुनः बोलें या हाथ से टाइप करें।",
      emptyPrompt: "बोलने के लिए माइक दबाएं या ऊपर अपना अनुरोध लिखें।",
    },
    passengerLogin: {
      title: "यात्री स्वागत",
      subtitle: "अपनी सीट को केबिन क्रू सिस्टम से कनेक्ट करें",
      seatLabel: "सीट संख्या",
      seatPlaceholder: "उदा. 18A, 24K",
      inviteCode: "फ़्लाइट इनवाइट कोड",
      invitePlaceholder: "इनवाइट कोड दर्ज करें",
      enterButton: "केबिन सेवा शुरू करें",
      loggingIn: "सीट सत्यापित हो रही है...",
      seatError: "कृपया एक वैध सीट संख्या दर्ज करें (उदा. 18A)।",
      codeError: "कृपया इनवाइट कोड दर्ज करें।",
    },
    crew: {
      dashboardTitle: "केबिन क्रू कार्य सूची",
      dashboardSubtitle: "अधिकृत उड़ान सेवा केंद्र",
      urgentBadge: "अत्यावश्यक प्राथमिकता",
      routineBadge: "सामान्य",
      queueSummary: "वर्तमान केबिन कतार",
      emptyQueue: "कतार खाली है",
      emptyQueueSub: "सभी यात्री अनुरोध पूरे हो चुके हैं।",
      actionAcknowledge: "स्वीकार करें",
      actionAcknowledged: "स्वीकृत",
      actionSendReply: "पूर्व-निर्धारित उत्तर भेजें",
      actionComplete: "पूर्ण करें",
      actionCompleted: "पूर्ण",
      paTitle: "केबिन सार्वजनिक घोषणा (PA)",
      paSelectCard: "स्वीकृत घोषणा कार्ड चुनें",
      paDuration: "प्रसारण अवधि",
      paBroadcastAction: "केबिन में प्रसारित करें",
      paActiveNotice: "सक्रिय केबिन घोषणा",
      paEndAction: "घोषणा समाप्त करें",
      loginTitle: "क्रू लॉगिन पोर्टल",
      loginSubtitle: "अपने सुरक्षा पिन के साथ लॉगिन करें",
      pinLabel: "क्रू सुरक्षा पिन",
      pinPlaceholder: "पिन दर्ज करें",
      loginButton: "डैशबोर्ड खोलें",
      pinError: "अमान्य पिन। कृपया जांचें।",
      filterAll: "सभी",
      filterPending: "लंबित",
      filterAcknowledged: "स्वीकृत",
      filterCompleted: "पूर्ण",
    },
    replyModal: {
      title: "पूर्व-निर्धारित उत्तर चुनें",
      selectReply: "स्वीकृत उत्तरों की सूची में से चुनें (मुक्त टेक्स्ट अनुमत नहीं है):",
      sendButton: "यात्री को उत्तर भेजें",
      cancelButton: "रद्द करें",
    },
    actions: {
      cancel: "अनुरोध रद्द करें",
      confirm: "पुष्टि करें और भेजें",
      close: "बंद करें",
      sendRequest: "अनुरोध भेजें",
      viewDetails: "विवरण",
      hearReply: "उत्तर सुनने के लिए टैप करें",
      logout: "लॉग आउट",
    },
  },
  ta: {
    appName: "SoraLink",
    tagline: "விமானப் பயணிகள் உதவி சேவை",
    subTagline: "கேபின் குழுவினர் நேரடி இணைப்பு",
    heading: "நாங்கள் உங்களுக்கு எவ்வாறு உதவலாம்?",
    subheading: "உங்கள் இருக்கையிலேயே அக்கறையான கேபின் சேவை",
    supportingText:
      "கீழே உள்ள சேவையைத் தேர்வுசெய்யவும் அல்லது பணிப்பெண்களிடம் பேச குரல்வழியைப் பயன்படுத்தவும்.",
    speakButton: "குரல் மூலம் கோரிக்கை விடுக்கவும்",
    speakSubtext: "தொட்டு இயல்பாகப் பேசுங்கள்",
    typedButton: "தட்டச்சு செய்து கோரவும்",
    typedSubtext: "அங்கீகரிக்கப்பட்ட பிரிவுகளில் இருந்து தேர்ந்தெடுக்கவும்",
    activeRequestsHeading: "செயலில் உள்ள விமானக் கோரிக்கைகள்",
    noActiveRequests: "தற்போது செயலில் கோரிக்கைகள் இல்லை",
    noActiveRequestsSub:
      "உதவி பெற மேலே உள்ள ஏதேனும் அட்டையைத் தட்டவும் அல்லது மைக்ரோஃபோனைத் தொடவும்.",
    offlineNotice: "சாதனம் தற்போது இணைப்பில் இல்லை. கேபின் வைஃபையுடன் மீண்டும் இணைக்கவும்.",
    categories: {
      water_request: {
        label: "குடிநீர்",
        subLabel: "Water",
        description: "தூய குடிநீர் (குளிர்ந்த, சாதாரண அல்லது வெதுவெதுப்பான).",
        shortBadge: "பானம்",
      },
      blanket_request: {
        label: "போர்வை",
        subLabel: "Blanket",
        description: "உங்கள் வசதிக்காகத் தூய்மையான கேபின் போர்வை.",
        shortBadge: "வசதி",
      },
      pillow_request: {
        label: "தலையணை",
        subLabel: "Pillow",
        description: "பயணத்தின் போது ஓய்வெடுக்க வசதியான தலையணை.",
        shortBadge: "ஓய்வு",
      },
      accessibility_assist: {
        label: "மாற்றுத்திறனாளி உதவி",
        subLabel: "Accessibility",
        description: "நகர்தல், அமருதல் அல்லது முன்னுரிமை உதவி.",
        shortBadge: "முன்னுரிமை",
      },
    },
    statuses: {
      PENDING: {
        title: "குழுவினரின் பார்வைக்காகக் காத்திருக்கிறது",
        desc: "கோரிக்கை சமர்ப்பிக்கப்பட்டது, கேபின் குழுவின் உறுதிப்படுத்தலுக்குக் காத்திருக்கிறது.",
      },
      ACKNOWLEDGED: {
        title: "பணிப்பாளர் நியமிக்கப்பட்டார்",
        desc: "கேபின் பணிப்பாளர் உங்கள் கோரிக்கையை ஏற்றுத் தயாரித்து வருகிறார்.",
      },
      COMPLETED: {
        title: "நிறைவடைந்தது",
        desc: "இந்த கேபின் சேவை வெற்றிகரமாக நிறைவேற்றப்பட்டது.",
      },
      CANCELLED: {
        title: "ரத்து செய்யப்பட்டது",
        desc: "இக்கோரிக்கை பயணியால் ரத்து செய்யப்பட்டது.",
      },
    },
    priorities: {
      URGENT: "அவசரம்",
      ROUTINE: "வழக்கமானது",
    },
    voice: {
      title: "குரல் உரை மதிப்பாய்வு",
      tapToSpeak: "பேச மைக்கை அழுத்தவும்",
      listening: "உங்கள் கோரிக்கை கேட்கப்படுகிறது...",
      unsupported:
        "இந்த உலாவியில் குரல் அங்கீகாரம் ஆதரிக்கப்படவில்லை. நீங்கள் கீழே தட்டச்சு செய்யலாம்.",
      transcriptLabel: "நாங்கள் கேட்டது (திருத்தக்கூடியது)",
      transcriptPlaceholder:
        "மைக் மூலம் பேசவும் அல்லது உங்கள் கோரிக்கையை இங்கே தட்டச்சு செய்யவும்...",
      suggestedIntent: "பரிந்துரைக்கப்பட்ட கோரிக்கை",
      confidence: "நம்பகத்தன்மை மதிப்பீடு",
      attributes: "விருப்பங்கள் & விவரக்குறிப்புகள்",
      alternatives: "அங்கீகரிக்கப்பட்ட மாற்று விருப்பங்கள்",
      confirmSend: "உறுதிசெய்து குழுவினருக்கு அனுப்பவும்",
      submitting: "அனுப்பப்படுகிறது...",
      outcomeSuggested: "உயர் துல்லியத்துடன் அங்கீகரிக்கப்பட்டது",
      outcomeRequiresChoice: "பல தேர்வுகள் சாத்தியம் — தயவுசெய்து தேர்ந்தெடுக்கவும்",
      outcomeUnreliable: "குறைந்த துல்லியம் — தயவுசெய்து கவனமாகச் சரிபார்க்கவும்",
      errorCapture:
        "குரலைத் தெளிவாகக் கேட்க முடியவில்லை. மீண்டும் பேசவும் அல்லது கைமுறையாகத் தட்டச்சு செய்யவும்.",
      emptyPrompt: "பேச மைக்கைத் தட்டவும் அல்லது மேலே தட்டச்சு செய்யவும்.",
    },
    passengerLogin: {
      title: "பயணிகள் வரவேற்பு",
      subtitle: "உங்கள் இருக்கையை கேபின் குழு அமைப்புடன் இணைக்கவும்",
      seatLabel: "இருக்கை எண்",
      seatPlaceholder: "எ.கா. 18A, 24K",
      inviteCode: "விமான அழைப்புக் குறியீடு",
      invitePlaceholder: "அழைப்புக் குறியீட்டை உள்ளிடவும்",
      enterButton: "சேவையைத் தொடங்கவும்",
      loggingIn: "இருக்கை சரிபார்க்கப்படுகிறது...",
      seatError: "சரியான இருக்கை எண்ணை உள்ளிடவும் (எ.கா. 18A).",
      codeError: "அழைப்புக் குறியீட்டை உள்ளிடவும்.",
    },
    crew: {
      dashboardTitle: "கேபின் குழுவினர் பணிப்பட்டியல்",
      dashboardSubtitle: "அங்கீகரிக்கப்பட்ட விமான சேவை நிலையம்",
      urgentBadge: "அவசர முன்னுரிமை",
      routineBadge: "வழக்கமானது",
      queueSummary: "தற்போதைய கேபின் வரிசை",
      emptyQueue: "வரிசை காலியாக உள்ளது",
      emptyQueueSub: "அனைத்துப் பயணிகளின் கோரிக்கைகளும் நிறைவேற்றப்பட்டன.",
      actionAcknowledge: "ஏற்றுக்கொள்",
      actionAcknowledged: "ஏற்கப்பட்டது",
      actionSendReply: "முன் அமைக்கப்பட்ட பதிலை அனுப்பு",
      actionComplete: "முடிக்கவும்",
      actionCompleted: "முடிந்தது",
      paTitle: "கேபின் பொது அறிவிப்பு (PA)",
      paSelectCard: "அங்கீகரிக்கப்பட்ட அறிவிப்பு அட்டையைத் தேர்வுசெய்க",
      paDuration: "ஒளிபரப்பு காலம்",
      paBroadcastAction: "கேபினில் ஒளிபரப்பவும்",
      paActiveNotice: "செயலில் உள்ள அறிவிப்பு",
      paEndAction: "அறிவிப்பை முடிக்கவும்",
      loginTitle: "குழுவினர் உள்நுழைவு",
      loginSubtitle: "உங்கள் பாதுகாப்புக் குறியீட்டுடன் உள்நுழையவும்",
      pinLabel: "குழுவினர் பாதுகாப்பு PIN",
      pinPlaceholder: "PIN உள்ளிடவும்",
      loginButton: "டாஷ்போர்டைத் திறக்கவும்",
      pinError: "தவறான PIN. தயவுசெய்து சரிபார்க்கவும்.",
      filterAll: "அனைத்தும்",
      filterPending: "நிலுவையில்",
      filterAcknowledged: "ஏற்கப்பட்டது",
      filterCompleted: "முடிந்தது",
    },
    replyModal: {
      title: "முன் அமைக்கப்பட்ட பதிலைத் தேர்ந்தெடுக்கவும்",
      selectReply: "அங்கீகரிக்கப்பட்ட பதில்களிலிருந்து தேர்ந்தெடுக்கவும்:",
      sendButton: "பயணிக்குப் பதில் அனுப்பு",
      cancelButton: "ரத்துசெய்",
    },
    actions: {
      cancel: "கோரிக்கையை ரத்துசெய்",
      confirm: "உறுதிசெய்து அனுப்பு",
      close: "மூடு",
      sendRequest: "கோரிக்கை அனுப்பு",
      viewDetails: "விவரங்கள்",
      hearReply: "பதிலைக் கேட்க தட்டவும்",
      logout: "வெளியேறு",
    },
  },
  mr: {
    appName: "SoraLink",
    tagline: "विमानातील प्रवासी साहाय्य",
    subTagline: "केबिन क्रू थेट संपर्क",
    heading: "आम्ही आपली काय मदत करू शकतो?",
    subheading: "आपल्या जागेवरच तत्पर आणि आदरयुक्त केबिन सेवा",
    supportingText:
      "खालील सेवा निवडा किंवा केबिन कर्मचाऱ्यांशी बोलण्यासाठी आवाजाचा वापर करा.",
    speakButton: "बोलून विनंती करा",
    speakSubtext: "स्पर्श करा आणि सहजतेने बोला",
    typedButton: "टाइप करून विनंती करा",
    typedSubtext: "मान्यताप्राप्त प्रकारांमधून निवडा",
    activeRequestsHeading: "सध्याच्या उड्डाण विनंत्या",
    noActiveRequests: "सध्या कोणतीही सक्रिय विनंती नाही",
    noActiveRequestsSub:
      "मदत मिळवण्यासाठी वरील कोणत्याही कार्डावर टॅप करा किंवा मायक्रोफोनला स्पर्श करा.",
    offlineNotice: "डिव्हाइस सध्या ऑफलाइन आहे. कृपया केबिन वाय-फायशी पुन्हा कनेक्ट करा.",
    categories: {
      water_request: {
        label: "पिण्याचे पाणी",
        subLabel: "Water",
        description: "ताजे पिण्याचे पाणी (थंड, सामान्य किंवा कोमट).",
        shortBadge: "पेय",
      },
      blanket_request: {
        label: "ब्लँकेट",
        subLabel: "Blanket",
        description: "आपल्या सोयीसाठी स्वच्छ केबिन ब्लँकेट.",
        shortBadge: "आराम",
      },
      pillow_request: {
        label: "उशी",
        subLabel: "Pillow",
        description: "विमानात विश्रांतीसाठी आरामदायी उशी.",
        shortBadge: "विश्रांती",
      },
      accessibility_assist: {
        label: "सुलभता साहाय्य",
        subLabel: "Accessibility",
        description: "हालचाल, बसणे किंवा विशेष साहाय्यासाठी प्राधान्य सेवा.",
        shortBadge: "प्राधान्य",
      },
    },
    statuses: {
      PENDING: {
        title: "कर्मचारी पडताळणी प्रलंबित",
        desc: "विनंती नोंदवली आहे, केबिन कर्मचाऱ्यांच्या मंजुरीची प्रतीक्षा आहे.",
      },
      ACKNOWLEDGED: {
        title: "कर्मचारी नियुक्त",
        desc: "केबिन कर्मचाऱ्यांनी आपली विनंती स्वीकारली असून तयारी सुरू आहे.",
      },
      COMPLETED: {
        title: "विनंती पूर्ण",
        desc: "ही केबिन सेवा यशस्वीरीत्या पूर्ण झाली आहे.",
      },
      CANCELLED: {
        title: "रद्द केली",
        desc: "ही विनंती प्रवाशाने रद्द केली आहे.",
      },
    },
    priorities: {
      URGENT: "तातडीचे",
      ROUTINE: "नेहमीचे",
    },
    voice: {
      title: "व्हॉइस मजकूर पडताळणी",
      tapToSpeak: "बोलण्यासाठी माइक टॅप करा",
      listening: "आपली विनंती ऐकली जात आहे...",
      unsupported:
        "या ब्राउझरमध्ये आवाज ओळखण्याची सुविधा उपलब्ध नाही. आपण खाली टाइप करू शकता.",
      transcriptLabel: "आम्ही ऐकलेला मजकूर (संपादनक्षम)",
      transcriptPlaceholder: "माइकद्वारे बोला किंवा आपली विनंती येथे टाइप करा...",
      suggestedIntent: "सुचवलेली विनंती",
      confidence: "अचूकता स्कोअर",
      attributes: "पर्याय आणि प्राधान्ये",
      alternatives: "मान्यताप्राप्त पर्यायी विनंत्या",
      confirmSend: "खात्री करा आणि कर्मचाऱ्यांना पाठवा",
      submitting: "पाठवत आहे...",
      outcomeSuggested: "उच्च अचूकतेने ओळखले",
      outcomeRequiresChoice: "अनेक पर्याय शक्य — कृपया निवडा",
      outcomeUnreliable: "कमी अचूकता — कृपया काळजीपूर्वक तपासा",
      errorCapture:
        "आवाज स्पष्टपणे ऐकू आला नाही. कृपया पुन्हा बोला किंवा स्वतः टाइप करा.",
      emptyPrompt: "बोलण्यासाठी माइक टॅप करा किंवा वर विनंती लिहा.",
    },
    passengerLogin: {
      title: "प्रवासी स्वागत",
      subtitle: "आपली जागा केबिन क्रू प्रणालीशी जोडा",
      seatLabel: "सीट क्रमांक",
      seatPlaceholder: "उदा. 18A, 24K",
      inviteCode: "उड्डाण आमंत्रण कोड",
      invitePlaceholder: "आमंत्रण कोड प्रविष्ट करा",
      enterButton: "केबिन सेवा सुरू करा",
      loggingIn: "जागेची पडताळणी सुरू आहे...",
      seatError: "कृपया वैध सीट क्रमांक प्रविष्ट करा (उदा. 18A).",
      codeError: "कृपया आमंत्रण कोड प्रविष्ट करा.",
    },
    crew: {
      dashboardTitle: "केबिन क्रू कार्य रांग",
      dashboardSubtitle: "अधिकृत उड्डाण सेवा केंद्र",
      urgentBadge: "तातडीचे प्राधान्य",
      routineBadge: "नेहमीचे",
      queueSummary: "सध्याची केबिन रांग",
      emptyQueue: "रांग रिकामी आहे",
      emptyQueueSub: "सर्व प्रवाशांच्या विनंत्या पूर्ण झाल्या आहेत.",
      actionAcknowledge: "स्वीकारा",
      actionAcknowledged: "स्वीकारले",
      actionSendReply: "पूर्वनिर्धारित उत्तर पाठवा",
      actionComplete: "पूर्ण करा",
      actionCompleted: "पूर्ण",
      paTitle: "केबिन सार्वजनिक घोषणा (PA)",
      paSelectCard: "मान्यताप्राप्त घोषणा कार्ड निवडा",
      paDuration: "प्रसारण कालावधी",
      paBroadcastAction: "केबिनमध्ये प्रसारित करा",
      paActiveNotice: "सक्रिय केबिन घोषणा",
      paEndAction: "घोषणा समाप्त करा",
      loginTitle: "क्रू लॉगिन पोर्टल",
      loginSubtitle: "आपल्या सुरक्षा पिनसह लॉगिन करा",
      pinLabel: "क्रू सुरक्षा पिन",
      pinPlaceholder: "पिन प्रविष्ट करा",
      loginButton: "डॅशबोर्ड उघडा",
      pinError: "अवैध पिन. कृपया तपासा.",
      filterAll: "सर्व",
      filterPending: "प्रलंबित",
      filterAcknowledged: "स्वीकारलेले",
      filterCompleted: "पूर्ण",
    },
    replyModal: {
      title: "पूर्वनिर्धारित उत्तर निवडा",
      selectReply: "मान्यताप्राप्त उत्तरांमधून निवडा:",
      sendButton: "प्रवाशाला उत्तर पाठवा",
      cancelButton: "रद्द करा",
    },
    actions: {
      cancel: "विनंती रद्द करा",
      confirm: "खात्री करा आणि पाठवा",
      close: "बंद करा",
      sendRequest: "विनंती पाठवा",
      viewDetails: "तपशील",
      hearReply: "उत्तर ऐकण्यासाठी टॅप करा",
      logout: "लॉग आउट",
    },
  },
}
