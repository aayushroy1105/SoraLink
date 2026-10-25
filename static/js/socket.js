/* ==========================================================================
   SoraLink (空連) — Shared Offline Runtime, Socket.IO Manager, API & i18n
   ========================================================================== */

(function (window) {
  "use strict";

  const STORAGE_KEYS = {
    LANG: "soralink_ui_lang",
    MUTED: "soralink_sound_muted",
    LOCAL_META: "soralink_request_meta_v1",
    CREW_REPLIES: "soralink_crew_replies_v1",
  };

  const SUPPORTED_LANGUAGES = [
    { code: "en", nativeName: "English", label: "EN · English", speechLang: "en-US" },
    { code: "ja", nativeName: "日本語", label: "JA · 日本語", speechLang: "ja-JP" },
    { code: "zh", nativeName: "繁體中文", label: "ZH · 繁體中文", speechLang: "zh-TW" },
    { code: "hi", nativeName: "हिन्दी", label: "HI · हिन्दी", speechLang: "hi-IN" },
    { code: "ta", nativeName: "தமிழ்", label: "TA · தமிழ்", speechLang: "ta-IN" },
    { code: "mr", nativeName: "मराठी", label: "MR · मराठी", speechLang: "mr-IN" },
    { code: "pa", nativeName: "ਪੰਜਾਬੀ", label: "PA · ਪੰਜਾਬੀ", speechLang: "pa-IN" },
  ];

  // Canonical 15 Intents (synced with SoraLink-integration/data/intents.json + Figma translations.ts & canonicalData.ts)
  const CANONICAL_INTENTS = [
    {
      id: "water_request",
      priority: "ROUTINE",
      isPrimary: true,
      kanji: "水",
      labels: {
        en: "Water",
        ja: "お水",
        zh: "飲用水",
        hi: "पीने का पानी",
        ta: "குடிநீர்",
        mr: "पिण्याचे पाणी",
        pa: "ਪਾਣੀ ਦੀ ਬੇਨਤੀ",
      },
      subLabels: {
        en: "お水",
        ja: "Water",
        zh: "お水",
        hi: "Water",
        ta: "Water",
        mr: "Water",
        pa: "Water",
      },
      descriptions: {
        en: "Fresh drinking water (cold, room temperature, or warm).",
        ja: "新鮮な飲用水（冷水・常温・白湯）をご用意します。",
        zh: "純淨飲用水（冷水、常溫或溫熱）。",
        hi: "ताज़ा पीने का पानी (ठंडा, सामान्य या गुनगुना)।",
        ta: "தூய குடிநீர் (குளிர்ந்த, சாதாரண அல்லது வெதுவெதுப்பான).",
        mr: "ताजे पिण्याचे पाणी (थंड, सामान्य किंवा कोमट).",
      },
      hasTemperature: true,
    },
    {
      id: "blanket_request",
      priority: "ROUTINE",
      isPrimary: true,
      kanji: "毛",
      labels: {
        en: "Blanket",
        ja: "毛布",
        zh: "毛毯",
        hi: "कंबल",
        ta: "போர்வை",
        mr: "ब्लँकेट",
        pa: "ਕੰਬਲ ਦੀ ਬੇਨਤੀ",
      },
      subLabels: {
        en: "毛布",
        ja: "Blanket",
        zh: "毛布",
        hi: "Blanket",
        ta: "Blanket",
        mr: "Blanket",
        pa: "Blanket",
      },
      descriptions: {
        en: "Freshly laundered cabin blanket for your comfort.",
        ja: "清潔な機内用ブランケットをお届けします。",
        zh: "潔淨舒適客艙毛毯。",
        hi: "आपकी सुविधा के लिए स्वच्छ केबिन कंबल।",
        ta: "உங்கள் வசதிக்காகத் தூய்மையான கேபின் போர்வை.",
        mr: "आपल्या सोयीसाठी स्वच्छ केबिन ब्लँकेट.",
      },
    },
    {
      id: "pillow_request",
      priority: "ROUTINE",
      isPrimary: true,
      kanji: "枕",
      labels: {
        en: "Pillow",
        ja: "枕",
        zh: "枕頭",
        hi: "तकिया",
        ta: "தலையணை",
        mr: "उशी",
        pa: "ਸਿਰਹਾਣੇ ਦੀ ਬੇਨਤੀ",
      },
      subLabels: {
        en: "枕",
        ja: "Pillow",
        zh: "枕",
        hi: "Pillow",
        ta: "Pillow",
        mr: "Pillow",
        pa: "Pillow",
      },
      descriptions: {
        en: "Supportive in-flight rest pillow.",
        ja: "休息をサポートするお座席用枕です。",
        zh: "舒適休息之客艙靠枕。",
        hi: "उड़ान में आराम के लिए आरामदायक तकिया।",
        ta: "பயணத்தின் போது ஓய்வெடுக்க வசதியான தலையணை.",
        mr: "विमानात विश्रांतीसाठी आरामदायी उशी.",
      },
    },
    {
      id: "accessibility_assist",
      priority: "URGENT",
      isPrimary: true,
      kanji: "介",
      labels: {
        en: "Accessibility assistance",
        ja: "お手伝い・移動サポート",
        zh: "行動與無障礙協助",
        hi: "सुलभता सहायता",
        ta: "மாற்றுத்திறனாளி உதவி",
        mr: "सुलभता साहाय्य",
        pa: "ਸਹਾਇਤਾ ਦੀ ਲੋੜ",
      },
      subLabels: {
        en: "お手伝い",
        ja: "Accessibility",
        zh: "お手伝い",
        hi: "Accessibility",
        ta: "Accessibility",
        mr: "Accessibility",
        pa: "Accessibility",
      },
      descriptions: {
        en: "Urgent mobility, seating, or accessibility support.",
        ja: "移動やお座席での介助など優先サポートです。",
        zh: "行動支援、移動或優先照護需求。",
        hi: "गतिशीलता, बैठने या विशेष सहायता के लिए प्राथमिकता सेवा।",
        ta: "நகர்தல், அமருதல் அல்லது முன்னுரிமை உதவி.",
        mr: "हालचाल, बसणे किंवा विशेष साहाय्यासाठी प्राधान्य सेवा.",
      },
    },
    {
      id: "medical_help",
      priority: "URGENT",
      isPrimary: false,
      kanji: "医",
      labels: {
        en: "Medical Assistance",
        ja: "医療救護・体調不良",
        zh: "醫療與身體不適協助",
        hi: "चिकित्सा सहायता",
        ta: "மருத்துவ உதவி",
        mr: "वैद्यकीय साहाय्य",
        pa: "ਡਾਕਟਰੀ ਮਦਦ ਦੀ ਲੋੜ",
      },
      subLabels: { en: "医療救護", ja: "Medical" },
      descriptions: {
        en: "Passenger requests urgent medical care or attention.",
        ja: "救急対応または体調不良のサポートを要請します。",
        zh: "請求緊急醫療照護或協助。",
        hi: "यात्री तत्काल चिकित्सा देखभाल या ध्यान देने का अनुरोध करते हैं।",
        ta: "பயணி அவசர மருத்துவ சிகிச்சை அல்லது கவனிப்பைக் கோருகிறார்.",
        mr: "प्रवासी तातडीच्या वैद्यकीय मदतीची विनंती करतात.",
      },
    },
    {
      id: "motion_sickness",
      priority: "URGENT",
      isPrimary: false,
      kanji: "酔",
      labels: {
        en: "Motion Sickness Care",
        ja: "乗り物酔いケア",
        zh: "暈機不適照護",
        hi: "मोशन सिकनेस देखभाल",
        ta: "பயணக் குமட்டல் கவனிப்பு",
        mr: "मोशन सिकनेस साहाय्य",
        pa: "ਚੱਕਰ ਜਾਂ ਉਲਟੀ ਦੀ ਮਦਦ",
      },
      subLabels: { en: "乗り物酔い", ja: "Motion Care" },
      descriptions: {
        en: "Passenger requests motion sickness bag, relief, or care.",
        ja: "乗り物酔いのケアやエチケット袋を要請します。",
        zh: "請求暈機清潔袋或不適照護。",
        hi: "यात्री मोशन सिकनेस बैग, राहत या देखभाल का अनुरोध करते हैं।",
        ta: "பயணி குமட்டல் பை அல்லது நிவாரணத்தைக் கோருகிறார்.",
        mr: "प्रवासी मळमळ किंवा अस्वस्थतेसाठी मदतीची विनंती करतात.",
      },
    },
    {
      id: "safety_concern",
      priority: "URGENT",
      isPrimary: false,
      kanji: "安",
      labels: {
        en: "Safety Concern",
        ja: "安全上の懸念・確認",
        zh: "安全疑慮與確認",
        hi: "सुरक्षा चिंता",
        ta: "பாதுகாப்புக் கவலை",
        mr: "सुरक्षा चिंता",
        pa: "ਸੁਰੱਖਿਆ ਸੰਬੰਧੀ ਚਿੰਤਾ",
      },
      subLabels: { en: "安全確認", ja: "Safety" },
      descriptions: {
        en: "Passenger reports a safety, seatbelt, or cabin hazard.",
        ja: "安全上の懸念事項について乗務員へ報告します。",
        zh: "向機組人員通報安全問題或客艙狀況。",
        hi: "यात्री सुरक्षा, सीटबेल्ट या केबिन खतरे की रिपोर्ट करते हैं।",
        ta: "பயணி பாதுகாப்பு அல்லது கேபின் ஆபத்து குறித்து தெரிவிக்கிறார்.",
        mr: "प्रवासी सुरक्षा, सीटबेल्ट किंवा धोक्याची तक्रार करतात.",
      },
    },
    {
      id: "tea_coffee",
      priority: "ROUTINE",
      isPrimary: false,
      kanji: "茶",
      labels: {
        en: "Tea or Coffee",
        ja: "お茶・コーヒー",
        zh: "茶飲或咖啡",
        hi: "चाय या कॉफ़ी",
        ta: "தேநீர் அல்லது காபி",
        mr: "चहा किंवा कॉफी",
        pa: "ਚਾਹ ਜਾਂ ਕੌਫੀ ਦੀ ਬੇਨਤੀ",
      },
      subLabels: { en: "お茶・珈琲", ja: "Tea / Coffee" },
      descriptions: {
        en: "Request Japanese green tea, black tea, or coffee.",
        ja: "日本茶（緑茶）・紅茶・ホットコーヒーをご用意します。",
        zh: "提供日本綠茶、紅茶或熱咖啡。",
        hi: "हरी चाय, काली चाय या गर्म कॉफ़ी का अनुरोध करें।",
        ta: "கிரீன் டீ, பிளாக் டீ அல்லது சூடான காபி.",
        mr: "ग्रीन टी, ब्लॅक टी किंवा गरम कॉफी.",
      },
    },
    {
      id: "meal_inquiry",
      priority: "ROUTINE",
      isPrimary: false,
      kanji: "食",
      labels: {
        en: "Meal Inquiry",
        ja: "お食事のお問い合わせ",
        zh: "餐點諮詢",
        hi: "भोजन संबंधी पूछताछ",
        ta: "உணவு பற்றிய விசாரணை",
        mr: "जेवणाविषयी विचारणा",
        pa: "ਭੋਜਨ ਬਾਰੇ ਪੁੱਛਗਿੱਛ",
      },
      subLabels: { en: "機内食", ja: "Meal Service" },
      descriptions: {
        en: "Inquire about meal schedule or dietary options.",
        ja: "機内食の配膳予定やお食事内容についてお尋ねします。",
        zh: "詢問機上餐點供應時間或菜單內容。",
        hi: "भोजन समय या आहार विकल्पों के बारे में पूछें।",
        ta: "உணவு நேரம் அல்லது விருப்பங்கள் பற்றி கேளுங்கள்.",
        mr: "जेवणाची वेळ किंवा आहाराच्या पर्यायांबद्दल विचारा.",
      },
      hasDietary: true,
    },
    {
      id: "headphone_request",
      priority: "ROUTINE",
      isPrimary: false,
      kanji: "音",
      labels: {
        en: "Headphones",
        ja: "ヘッドホン",
        zh: "耳機",
        hi: "हेडफ़ोन",
        ta: "ஹெட்போன்கள்",
        mr: "हेडफोन",
        pa: "ਹੈੱਡਫੋਨ ਦੀ ਬੇਨਤੀ",
      },
      subLabels: { en: "ヘッドホン", ja: "Headphones" },
      descriptions: {
        en: "Request in-flight entertainment headphones or adapter.",
        ja: "機内エンターテインメント用ヘッドホンをお届けします。",
        zh: "提供機上娛樂系統耳機或轉接頭。",
        hi: "मनोरंजन प्रणाली के लिए हेडफ़ोन या एडाप्टर का अनुरोध करें।",
        ta: "பொழுதுபோக்கு அமைப்புக்கான ஹெட்போன்கள்.",
        mr: "मनोरंजन यंत्रणेसाठी हेडफोन किंवा अडॅप्टर.",
      },
    },
    {
      id: "bag_help",
      priority: "ROUTINE",
      isPrimary: false,
      kanji: "荷",
      labels: {
        en: "Cabin Baggage Help",
        ja: "手荷物のお手伝い",
        zh: "隨身行李協助",
        hi: "सामान रखने में सहायता",
        ta: "கைப்பை உதவி",
        mr: "सामान ठेवण्यास मदत",
        pa: "ਸਮਾਨ ਵਿੱਚ ਮਦਦ",
      },
      subLabels: { en: "手荷物", ja: "Baggage" },
      descriptions: {
        en: "Request assistance with overhead locker storage.",
        ja: "頭上荷物棚の収納や取り出しをお手伝いします。",
        zh: "協助頭頂行李艙收納或取件。",
        hi: "ओवरहेड लॉकर में सामान रखने या निकालने में सहायता।",
        ta: "மேலடுக்கு பெட்டகத்தில் பைகளை வைக்க உதவி.",
        mr: "डोक्यावरील लॉकरमध्ये सामान ठेवण्यासाठी मदत.",
      },
    },
    {
      id: "seat_issue",
      priority: "ROUTINE",
      isPrimary: false,
      kanji: "席",
      labels: {
        en: "Seat Controls / Tray Table",
        ja: "座席・テーブルの不調",
        zh: "座位控制與餐桌調整",
        hi: "सीट नियंत्रण / ट्रे टेबल",
        ta: "இருக்கை கட்டுப்பாடுகள் / மேஜை",
        mr: "सीट नियंत्रणे / ट्रे टेबल",
        pa: "ਸੀਟ ਵਿੱਚ ਸਮੱਸਿਆ",
      },
      subLabels: { en: "お座席調整", ja: "Seat Controls" },
      descriptions: {
        en: "Report a reclining control, tray table, or reading light issue.",
        ja: "リクライニングやテーブル、読書灯の不調をご報告します。",
        zh: "回報座椅傾斜、餐桌或閱讀燈問題。",
        hi: "सीट रिक्लाइन, ट्रे टेबल या रीडिंग लाइट समस्या बताएं।",
        ta: "இருக்கை சாய்வு, மேஜை அல்லது விளக்கு பிரச்சனை.",
        mr: "सीट, ट्रे टेबल किंवा वाचन दिव्याची अडचण सांगा.",
      },
    },
    {
      id: "lavatory_assist",
      priority: "ROUTINE",
      isPrimary: false,
      kanji: "手",
      labels: {
        en: "Lavatory Assistance",
        ja: "お手洗いのご案内",
        zh: "洗手間引導協助",
        hi: "शौचालय मार्गदर्शन",
        ta: "கழிவறை உதவி",
        mr: "शौचालय साहाय्य",
        pa: "ਵਾਸ਼ਰੂਮ ਲਈ ਮਦਦ",
      },
      subLabels: { en: "化粧室案内", ja: "Lavatory" },
      descriptions: {
        en: "Request assistance or status inquiry regarding lavatories.",
        ja: "お手洗いの空き状況やお席からのご案内を要請します。",
        zh: "查詢洗手間使用狀態或引導協助。",
        hi: "शौचालय की स्थिति या जाने में सहायता का अनुरोध करें।",
        ta: "கழிவறை இருப்பு அல்லது வழிகாட்டுதல் உதவி.",
        mr: "शौचालय उपलब्धता किंवा जाण्यासाठी साहाय्य.",
      },
    },
    {
      id: "customs_form",
      priority: "ROUTINE",
      isPrimary: false,
      kanji: "税",
      labels: {
        en: "Customs / Immigration Form",
        ja: "税関申告書・入国カード",
        zh: "海關申報單與入境卡",
        hi: "सीमा शुल्क / आव्रजन फॉर्म",
        ta: "சுங்க / குடியேற்ற படிவம்",
        mr: "सीमा शुल्क / इमिग्रेशन फॉर्म",
        pa: "ਕਸਟਮ ਫਾਰਮ ਦੀ ਮਦਦ",
      },
      subLabels: { en: "入国書類", ja: "Customs Form" },
      descriptions: {
        en: "Request an immigration card or pen for documentation.",
        ja: "入国カード・税関申告書や筆記用具をご用意します。",
        zh: "索取入境卡、海關申報單或填寫用筆。",
        hi: "आव्रजन कार्ड या लिखने के लिए पेन का अनुरोध करें।",
        ta: "குடியேற்ற அட்டை அல்லது எழுதுகோல் கோரவும்.",
        mr: "इमिग्रेशन कार्ड किंवा पेनची विनंती करा.",
      },
    },
    {
      id: "baby_care",
      priority: "ROUTINE",
      isPrimary: false,
      kanji: "児",
      labels: {
        en: "Baby Care Assistance",
        ja: "乳幼児サポート",
        zh: "嬰幼兒照護協助",
        hi: "शिशु देखभाल सहायता",
        ta: "குழந்தை பராமரிப்பு உதவி",
        mr: "शिशू काळजी साहाय्य",
        pa: "ਬੱਚੇ ਦੀ ਦੇਖਭਾਲ ਲਈ ਮਦਦ",
      },
      subLabels: { en: "乳幼児ケア", ja: "Baby Care" },
      descriptions: {
        en: "Request hot water for formula, infant belt, or diaper disposal.",
        ja: "調乳用のお湯や乳幼児用ベルトなどのお手伝いを要請します。",
        zh: "請求沖泡奶粉熱水、嬰兒安全帶或相關協助。",
        hi: "फॉर्मूला के लिए गर्म पानी, शिशु बेल्ट या डायपर सहायता।",
        ta: "சூடான தண்ணீர் அல்லது குழந்தை பாதுகாப்பு பெல்ட் உதவி.",
        mr: "गरम पाणी, बाळ सुरक्षा बेल्ट किंवा इतर मदत.",
      },
    },
  ];

  // Approved PA Cards Catalog (matches SoraLink-integration/data/pa_cards.json)
  const PA_CARDS_CATALOG = {
    turbulence: {
      id: "turbulence",
      category: "safety",
      default_ttl: 180,
      titles: {
        en: "Turbulence Reminder",
        ja: "揺れに伴うシートベルト着用のお願い",
        zh: "亂流安全提醒",
        hi: "टर्बुलेंस सुरक्षा सूचना",
        ta: "வளிமண்டல குலுக்கல் எச்சரிக்கை",
        mr: "टर्ब्युलन्स सुरक्षा सूचना",
      },
      bodies: {
        en: "Please return to your seat and fasten your seatbelt due to turbulence.",
        ja: "気流の乱れが予想されます。お席にお戻りになり、シートベルトをお締めください。",
        zh: "因氣流不穩，請返回座位並繫好安全帶。",
        hi: "हवा के दबाव के कारण कृपया अपनी सीट पर लौटें और सीटबेल्ट बांध लें।",
        ta: "காற்று சலனம் காரணமாக உங்கள் இருக்கைக்குத் திரும்பி சீட்பெல்ட்டை அணியுங்கள்.",
        mr: "हवेतील बदलामुळे कृपया आपल्या सीटवर बसा आणि सीटबेल्ट लावा.",
      },
    },
    meal_service: {
      id: "meal_service",
      category: "service",
      default_ttl: 180,
      titles: {
        en: "Meal Service",
        ja: "お食事・お飲み物サービスのご案内",
        zh: "餐飲服務開始",
        hi: "भोजन सेवा की सूचना",
        ta: "உணவு சேவை அறிவிப்பு",
        mr: "जेवण सेवा सूचना",
      },
      bodies: {
        en: "Cabin meal and beverage service is starting shortly.",
        ja: "まもなく機内食およびお飲み物のサービスを開始いたします。",
        zh: "機上餐點與飲品服務即將開始。",
        hi: "केबिन में भोजन और पेय सेवा शीघ्र ही शुरू होने वाली है।",
        ta: "விமான உணவு மற்றும் பான சேவை விரைவில் தொடங்க உள்ளது.",
        mr: "केबिनमध्ये जेवण आणि पेय सेवा लवकरच सुरू होत आहे.",
      },
    },
    arrival_preparation: {
      id: "arrival_preparation",
      category: "arrival",
      default_ttl: 180,
      titles: {
        en: "Arrival Preparation",
        ja: "着陸態勢へのご準備のお願い",
        zh: "準備降落提醒",
        hi: "आगमन की तैयारी",
        ta: "தரையிறங்கும் தயாரிப்பு",
        mr: "आगमनाची तयारी",
      },
      bodies: {
        en: "Please prepare for arrival by securing tray tables and personal items.",
        ja: "まもなく着陸態勢に入ります。テーブルと座席を元の位置にお戻しください。",
        zh: "飛機即將準備降落，請收起餐桌並妥善收好個人物品。",
        hi: "कृपया ट्रे टेबल बंद करें और आगमन के लिए अपने सामान को सुरक्षित रखें।",
        ta: "தயவுசெய்து மேஜைகளை மடித்து வைத்து தரையிறங்கத் தயாராகுங்கள்.",
        mr: "कृपया ट्रे टेबल बंद करा आणि उतरण्याच्या तयारीसाठी आपले सामान व्यवस्थित ठेवा.",
      },
    },
    boarding_update: {
      id: "boarding_update",
      category: "boarding",
      default_ttl: 120,
      titles: {
        en: "Boarding Update",
        ja: "ご搭乗・手荷物収納のご案内",
        zh: "登機與行李提醒",
        hi: "बोर्डिंग सूचना",
        ta: "விமான ஏற்றம் அறிவிப்பு",
        mr: "बोर्डिंग सूचना",
      },
      bodies: {
        en: "Boarding is in progress. Please keep the aisle clear and stow carry-on items.",
        ja: "現在ご搭乗案内中です。通路を空け、手荷物は上の棚または前の座席の下に収納してください。",
        zh: "正在登機中，請保持走道暢通並妥善放置隨身行李。",
        hi: "बोर्डिंग जारी है। कृपया गलियारा साफ रखें और अपना सामान निर्धारित स्थान पर रखें।",
        ta: "பயணிகள் ஏறிக்கொண்டிருக்கிறார்கள். நடைபாதையைத் தடையின்றி வைத்திருக்கவும்.",
        mr: "बोर्डिंग सुरू आहे. कृपया मधली वाट मोकळी ठेवा आणि सामान जाग्यावर ठेवा.",
      },
    },
    cabin_crew_assistance: {
      id: "cabin_crew_assistance",
      category: "service",
      default_ttl: 120,
      titles: {
        en: "Crew Assistance",
        ja: "客室乗務員のご対応状況について",
        zh: "機組人員服務提醒",
        hi: "केबिन क्रू सहायता सूचना",
        ta: "பணிக்குழு உதவி அறிவிப்பு",
        mr: "केबिन क्रू मदत सूचना",
      },
      bodies: {
        en: "Cabin crew are assisting passengers and will respond to routine requests shortly.",
        ja: "ただいま客室乗務員が順次対応しております。通常のリクエストには今しばらくお待ちください。",
        zh: "機組人員正在協助其他旅客，稍後將盡快處理一般服務請求。",
        hi: "केबिन क्रू अभी यात्रियों की सहायता कर रहे हैं और शीघ्र ही आपके अनुरोध का उत्तर देंगे।",
        ta: "பணிக்குழுவினர் மற்ற பயணிகளுக்கு உதவிக் கொண்டிருக்கிறார்கள், விரைவில் வருவார்கள்.",
        mr: "केबिन क्रू सध्या इतर प्रवाशांना मदत करत आहेत आणि लवकरच आपल्या विनंतीला प्रतिसाद देतील.",
      },
    },
    lavatory_queue: {
      id: "lavatory_queue",
      category: "cabin",
      default_ttl: 120,
      titles: {
        en: "Lavatory Reminder",
        ja: "化粧室ご利用時のお願い",
        zh: "洗手間使用提醒",
        hi: "शौचालय उपयोग सूचना",
        ta: "கழிப்பறை அறிவிப்பு",
        mr: "स्वच्छतागृह सूचना",
      },
      bodies: {
        en: "Please keep the aisle clear while waiting for the lavatory.",
        ja: "化粧室をお待ちの際は、安全のため通路をふさがないようご協力をお願いいたします。",
        zh: "等候洗手間時，請保持走道暢通以維安全。",
        hi: "शौचालय की प्रतीक्षा करते समय कृपया गलियारा साफ रखें।",
        ta: "கழிப்பறைக்காகக் காத்திருக்கும்போது நடைபாதையைத் தடையின்றி வைத்திருக்கவும்.",
        mr: "स्वच्छतागृहाची वाट पाहताना कृपया मधली वाट मोकळी ठेवा.",
      },
    },
  };

  // Approved Crew Fixed Responses (matches SoraLink-integration/data/crew_responses.json)
  const CREW_RESPONSES_CATALOG = {
    request_acknowledged: {
      id: "request_acknowledged",
      labels: {
        en: "Crew acknowledged your request.",
        ja: "乗務員が確認しました。",
        zh: "機組人員已確認您的請求。",
        hi: "क्रू ने आपका अनुरोध स्वीकार कर लिया है।",
        ta: "பணிக்குழு உங்கள் கோரிக்கையை ஏற்றுக்கொண்டது.",
        mr: "क्रूने तुमची विनंती स्वीकारली आहे.",
        pa: "ਕਰੂ ਨੇ ਤੁਹਾਡੀ ਬੇਨਤੀ ਵੇਖ ਲਈ ਹੈ",
      },
    },
    crew_on_the_way: {
      id: "crew_on_the_way",
      labels: {
        en: "Cabin crew have been notified and are on the way.",
        ja: "客室乗務員へ通知しました。まもなくお伺いします。",
        zh: "已通知機組人員，正在前往您的座位。",
        hi: "केबिन क्रू को सूचित कर दिया गया है और वे आ रहे हैं।",
        ta: "பணிக்குழுவினருக்குத் தெரிவிக்கப்பட்டுள்ளது, விரைவில் வருகிறார்கள்.",
        mr: "केबिन क्रूला कळवले आहे आणि ते येत आहेत.",
        pa: "ਕੈਬਿਨ ਕਰੂ ਨੂੰ ਸੂਚਿਤ ਕਰ ਦਿੱਤਾ ਗਿਆ ਹੈ",
      },
    },
    request_received: {
      id: "request_received",
      labels: {
        en: "Request received by cabin crew.",
        ja: "リクエストを受け付けました。",
        zh: "已收到您的服務請求。",
        hi: "आपका अनुरोध प्राप्त हो गया है।",
        ta: "உங்கள் கோரிக்கை பெறப்பட்டது.",
        mr: "तुमची विनंती प्राप्त झाली आहे.",
        pa: "ਬੇਨਤੀ ਪ੍ਰਾਪਤ ਹੋ ਗਈ ਹੈ",
      },
    },
    request_completed: {
      id: "request_completed",
      labels: {
        en: "Your request has been completed.",
        ja: "対応が完了しました。",
        zh: "您的服務請求已完成。",
        hi: "आपका अनुरोध पूरा हो गया है।",
        ta: "உங்கள் கோரிக்கை நிறைவேற்றப்பட்டது.",
        mr: "तुमची विनंती पूर्ण झाली आहे.",
        pa: "ਬੇਨਤੀ ਪੂਰੀ ਹੋ ਗਈ ਹੈ",
      },
    },
    request_unavailable: {
      id: "request_unavailable",
      labels: {
        en: "This item or service is temporarily unavailable.",
        ja: "ただいま対応できません。恐れ入りますがしばらくお待ちください。",
        zh: "此項服務暫時無法提供，敬請見諒。",
        hi: "यह सेवा अभी अस्थायी रूप से अनुपलब्ध है।",
        ta: "இந்த சேவை தற்காலிகமாக கிடைக்கவில்லை.",
        mr: "ही सेवा सध्या तात्पुरती अनुपलब्ध आहे.",
        pa: "ਇਹ ਬੇਨਤੀ ਇਸ ਵੇਲੇ ਉਪਲਬਧ ਨਹੀਂ ਹੈ",
      },
    },
    voice_not_understood: {
      id: "voice_not_understood",
      labels: {
        en: "Voice not clearly understood — please verify at seat.",
        ja: "音声を聞き取れませんでした。お席にて確認いたします。",
        zh: "語音未能清楚辨識，將由人員至座位確認。",
        hi: "आवाज़ स्पष्ट नहीं हुई — कृपया सीट पर पुष्टि करें।",
        ta: "குரல் தெளிவாகப் புரியவில்லை.",
        mr: "आवाज स्पष्ट समजला नाही.",
        pa: "ਆਵਾਜ਼ ਸਮਝ ਨਹੀਂ ਆਈ",
      },
    },
    offline_mode: {
      id: "offline_mode",
      labels: {
        en: "Operating in local cabin offline mode.",
        ja: "機内オフラインモードで動作中です。",
        zh: "正在使用機上離線模式。",
        hi: "लोकल केबिन ऑफ़लाइन मोड में कार्यरत।",
        ta: "ஆஃப்லைன் பயன்முறை.",
        mr: "ऑफलाइन मोड.",
        pa: "ਆਫਲਾਈਨ ਮੋਡ",
      },
    },
  };

  // UI String Dictionary across 6+ languages
  const UI_STRINGS = {
    seat: { en: "Seat", ja: "座席", zh: "座位", hi: "सीट", ta: "இருக்கை", mr: "सीट" },
    connected: { en: "Cabin LAN", ja: "機内接続中", zh: "機上連線", hi: "केबिन कनेक्टेड", ta: "இணைக்கப்பட்டுள்ளது", mr: "कनेक्टेड" },
    reconnecting: { en: "Reconnecting…", ja: "再接続中…", zh: "重新連線中…", hi: "पुनः कनेक्ट…", ta: "மீண்டும் இணைகிறது…", mr: "पुन्हा जोडत आहे…" },
    offline: { en: "Offline", ja: "オフライン", zh: "離線", hi: "ऑफ़लाइन", ta: "ஆஃப்லைன்", mr: "ऑफलाइन" },
    logout: { en: "Exit", ja: "退出", zh: "登出", hi: "बाहर", ta: "வெளியேறு", mr: "बाहेर" },
    cabinAnnouncement: { en: "Cabin Announcement", ja: "機内アナウンス", zh: "機艙廣播", hi: "केबिन घोषणा", ta: "விமான அறிவிப்பு", mr: "केबिन घोषणा" },
    howMayWeAssist: { en: "How may we assist you?", ja: "ご用件をお知らせください", zh: "請問需要什麼協助？", hi: "हम आपकी क्या सहायता कर सकते हैं?", ta: "நாங்கள் உங்களுக்கு எப்படி உதவலாம்?", mr: "आम्ही तुम्हाला कशी मदत करू शकतो?" },
    selectServiceSubtitle: {
      en: "Select a service card below, or speak in your preferred language.",
      ja: "下のカードを選択するか、ご希望の言語でお話しください。",
      zh: "請點選下方服務卡，或使用您熟悉的語言進行語音請求。",
      hi: "नीचे दिए गए कार्ड को चुनें, या अपनी भाषा में बोलकर बताएं।",
      ta: "கீழே உள்ள சேவையைத் தேர்ந்தெடுக்கவும் அல்லது உங்கள் மொழியில் பேசவும்.",
      mr: "खालील सेवा कार्ड निवडा किंवा तुमच्या भाषेत बोला.",
    },
    moreCategories: { en: "All 15 Cabin & Urgent Services", ja: "すべての機内サービス・緊急サポート (15種)", zh: "所有 15 項機上與緊急服務", hi: "सभी 15 केबिन और आपातकालीन सेवाएं", ta: "அனைத்து 15 விமான சேவைகள்", mr: "सर्व १५ केबिन आणि तातडीच्या सेवा" },
    speakRequest: { en: "Speak your request", ja: "音声でリクエストする", zh: "語音提出請求", hi: "बोलकर अनुरोध करें", ta: "குரல் மூலம் கோரிக்கை", mr: "बोलून विनंती करा" },
    speakRequestSub: { en: "Local AI voice recognition • Review before sending", ja: "機内AI音声認識 • 送信前に内容を確認できます", zh: "機上本地 AI 語音辨識 • 發送前可確認", hi: "लोकल AI आवाज़ पहचान • भेजने से पहले जांचें", ta: "உள்ளூர் AI குரல் அறிதல்", mr: "लोकल AI आवाज ओळख • पाठवण्यापूर्वी तपासा" },
    typeRequest: { en: "Type a custom request or note", ja: "テキストで入力・詳細を伝える", zh: "輸入文字請求或備註", hi: "टाइप करके अनुरोध भेजें", ta: "தட்டச்சு செய்து கோரிக்கை", mr: "टाइप करून विनंती करा" },
    inFlightRequests: { en: "Your Active Requests", ja: "リクエスト状況", zh: "您的服務請求狀態", hi: "आपके सक्रिय अनुरोध", ta: "உங்கள் கோரிக்கைகள்", mr: "तुमच्या विनंत्या" },
    noActiveRequests: { en: "No active requests yet.", ja: "現在リクエストはありません", zh: "目前沒有進行中的請求", hi: "अभी कोई सक्रिय अनुरोध नहीं है।", ta: "தற்போது கோரிக்கைகள் இல்லை.", mr: "सध्या कोणतीही विनंती नाही." },
    statusPending: { en: "Pending", ja: "受付済", zh: "待處理", hi: "प्रतीक्षारत", ta: "நிலுவையில்", mr: "प्रलंबित" },
    statusAcknowledged: { en: "Acknowledged", ja: "確認済", zh: "已確認", hi: "स्वीकृत", ta: "ஏற்றுக்கொள்ளப்பட்டது", mr: "स्वीकारले" },
    statusCompleted: { en: "Completed", ja: "完了", zh: "已完成", hi: "पूर्ण", ta: "முடிந்தது", mr: "पूर्ण" },
    priorityUrgent: { en: "Urgent", ja: "緊急", zh: "緊急", hi: "अत्यावश्यक", ta: "அவசரம்", mr: "तातडीचे" },
    priorityRoutine: { en: "Routine", ja: "通常", zh: "一般", hi: "सामान्य", ta: "வழக்கமான", mr: "सामान्य" },
    tapToHearReply: { en: "Tap to hear reply", ja: "音声で読み上げる", zh: "點選聆聽回覆", hi: "उत्तर सुनने के लिए टैप करें", ta: "பதிலைக் கேட்க தட்டவும்", mr: "उत्तर ऐकण्यासाठी टॅप करा" },
    crewMessage: { en: "Cabin Crew Reply", ja: "客室乗務員からのメッセージ", zh: "機組人員回覆", hi: "केबिन क्रू संदेश", ta: "பணிக்குழு செய்தி", mr: "केबिन क्रू संदेश" },
    confirmAndSend: { en: "Confirm & Send Request", ja: "確認して送信する", zh: "確認並發送請求", hi: "पुष्टि करें और भेजें", ta: "உறுதிப்படுத்தி அனுப்பவும்", mr: "पुष्टी करा आणि पाठवा" },
    cancel: { en: "Cancel", ja: "キャンセル", zh: "取消", hi: "रद्द करें", ta: "ரத்து செய்", mr: "रद्द करा" },
    waterTempLabel: { en: "Preferred Water Temperature", ja: "ご希望の温度", zh: "水溫偏好", hi: "पानी का तापमान", ta: "நீர் வெப்பநிலை", mr: "पाण्याचे तापमान" },
    tempCold: { en: "Cold", ja: "冷水", zh: "冰水", hi: "ठंडा", ta: "குளிர்ந்த", mr: "थंड" },
    tempRoom: { en: "Room Temp", ja: "常温", zh: "常溫", hi: "सामान्य", ta: "சாதாரண", mr: "सामान्य" },
    tempWarm: { en: "Warm", ja: "白湯・温水", zh: "溫熱水", hi: "गुनगुना", ta: "வெதுவெதுப்பான", mr: "कोमट" },
    dietaryLabel: { en: "Dietary Preference", ja: "お食事のタイプ", zh: "飲食偏好", hi: "भोजन विकल्प", ta: "உணவு விருப்பம்", mr: "जेवणाचा पर्याय" },
    dietVeg: { en: "Vegetarian", ja: "ベジタリアン", zh: "素食", hi: "शाकाहारी", ta: "சைவம்", mr: "शाकाहारी" },
    dietNonVeg: { en: "Standard", ja: "通常食", zh: "一般餐點", hi: "सामान्य", ta: "அசைவம்", mr: "सामान्य" },
    dietSnack: { en: "Light Snack", ja: "軽食・スナック", zh: "輕食點心", hi: "हल्का नाश्ता", ta: "சிற்றுண்டி", mr: "अल्पोपहार" },
    optionalNoteLabel: { en: "Additional Details (Optional)", ja: "補足メモ（任意）", zh: "補充說明（選填）", hi: "अतिरिक्त विवरण (वैकल्पिक)", ta: "கூடுதல் விவரங்கள்", mr: "अतिरिक्त तपशील (पर्यायी)" },
    statusDescPending: {
      en: "Sent to cabin crew console. A crew member will review your request shortly.",
      ja: "客室乗務員の端末へ送信されました。確認まで少々お待ちください。",
      zh: "已發送至機組人員終端，稍後將為您確認。",
      hi: "केबिन क्रू को भेज दिया गया है। शीघ्र ही इसकी समीक्षा की जाएगी।",
      ta: "பணிக்குழுவிற்கு அனுப்பப்பட்டது. விரைவில் கவனிக்கப்படும்.",
      mr: "केबिन क्रूकडे पाठवले आहे. लवकरच पाहिले जाईल.",
    },
    statusDescAck: {
      en: "Acknowledged by cabin crew. Assistance is being prepared for your seat.",
      ja: "乗務員が確認いたしました。お席へお伺いする準備をしております。",
      zh: "機組人員已確認，正在為您的座位準備服務。",
      hi: "केबिन क्रू द्वारा स्वीकार किया गया। आपकी सीट के लिए सहायता तैयार की जा रही है।",
      ta: "பணிக்குழுவால் ஏற்றுக்கொள்ளப்பட்டது. உதவி தயாராகிறது.",
      mr: "केबिन क्रूने स्वीकारले आहे. तुमच्या सीटसाठी मदत तयार केली जात आहे.",
    },
    statusDescCompleted: {
      en: "Completed by cabin crew. Need anything else? Feel free to submit another request.",
      ja: "対応が完了いたしました。ご不明な点がございましたら再度お知らせください。",
      zh: "此項服務已完成。若需要其他協助，歡迎隨時提出。",
      hi: "यह अनुरोध पूरा हो गया है।",
      ta: "இந்த கோரிக்கை நிறைவேற்றப்பட்டது.",
      mr: "ही विनंती पूर्ण झाली आहे.",
    },
  };

  function getLang() {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.LANG);
      if (saved && SUPPORTED_LANGUAGES.some((l) => l.code === saved)) {
        return saved;
      }
    } catch (_) {}
    return "en";
  }

  function setLang(lang) {
    if (!SUPPORTED_LANGUAGES.some((l) => l.code === lang)) return;
    try {
      localStorage.setItem(STORAGE_KEYS.LANG, lang);
    } catch (_) {}
    window.dispatchEvent(new CustomEvent("soralink:langchange", { detail: { lang } }));
  }

  function t(key, langOverride) {
    const lang = langOverride || getLang();
    const entry = UI_STRINGS[key];
    if (!entry) return key;
    return entry[lang] || entry.en || key;
  }

  function getIntentMeta(intentId) {
    return (
      CANONICAL_INTENTS.find((item) => item.id === intentId) || {
        id: intentId || "water_request",
        priority: "ROUTINE",
        isPrimary: false,
        kanji: "空",
        labels: { en: intentId || "Service Request" },
      }
    );
  }

  function getIntentTitle(intentId, langOverride) {
    const lang = langOverride || getLang();
    const meta = getIntentMeta(intentId);
    return (meta.labels && (meta.labels[lang] || meta.labels.en)) || intentId;
  }

  function getIntentSubLabel(intentId, langOverride) {
    const lang = langOverride || getLang();
    const meta = getIntentMeta(intentId);
    if (meta.subLabels) {
      return meta.subLabels[lang] || meta.subLabels.en || "";
    }
    return lang === "ja" ? (meta.labels && meta.labels.en) || "" : (meta.labels && meta.labels.ja) || "";
  }

  function getIntentDescription(intentId, langOverride) {
    const lang = langOverride || getLang();
    const meta = getIntentMeta(intentId);
    if (meta.descriptions) {
      return meta.descriptions[lang] || meta.descriptions.en || "";
    }
    return "";
  }

  function getPACardLocalized(paCardId, fallbackTitle, fallbackBody, langOverride) {
    const lang = langOverride || getLang();
    const card = PA_CARDS_CATALOG[paCardId];
    if (!card) {
      return {
        title: fallbackTitle || "Cabin Announcement",
        body: fallbackBody || "",
        bodyEn: fallbackBody || "",
        category: "cabin",
      };
    }
    return {
      title: (card.titles && (card.titles[lang] || card.titles.en)) || fallbackTitle || card.id,
      body: (card.bodies && (card.bodies[lang] || card.bodies.en)) || fallbackBody || "",
      bodyEn: (card.bodies && card.bodies.en) || fallbackBody || "",
      category: card.category || "cabin",
    };
  }

  function getCrewResponseText(responseId, fallbackLabels, langOverride) {
    const lang = langOverride || getLang();
    if (fallbackLabels && typeof fallbackLabels === "object" && fallbackLabels[lang]) {
      return fallbackLabels[lang];
    }
    const item = CREW_RESPONSES_CATALOG[responseId];
    if (item && item.labels) {
      return item.labels[lang] || item.labels.en;
    }
    if (fallbackLabels && typeof fallbackLabels === "object" && fallbackLabels.en) {
      return fallbackLabels.en;
    }
    return responseId || "";
  }

  // Synchronize frontend catalogs dynamically with GET /api/content/catalog
  async function syncCatalogFromServer() {
    try {
      const res = await apiFetch("/api/content/catalog");
      if (!res.ok || !res.data) return false;
      const data = res.data;

      if (Array.isArray(data.intents)) {
        for (const srvIntent of data.intents) {
          const id = srvIntent.id || srvIntent.intent_id;
          if (!id) continue;
          const existing = CANONICAL_INTENTS.find((i) => i.id === id);
          if (existing) {
            if (srvIntent.priority) existing.priority = srvIntent.priority;
            if (srvIntent.labels && typeof srvIntent.labels === "object") {
              existing.labels = Object.assign({}, srvIntent.labels, existing.labels);
            }
          } else {
            CANONICAL_INTENTS.push({
              id,
              priority: srvIntent.priority || "ROUTINE",
              isPrimary: Boolean(srvIntent.is_primary),
              kanji: "空",
              labels: srvIntent.labels || { en: id },
            });
          }
        }
      }

      if (Array.isArray(data.pa_cards)) {
        for (const srvCard of data.pa_cards) {
          const id = srvCard.id || srvCard.pa_card_id;
          if (!id) continue;
          if (!PA_CARDS_CATALOG[id]) {
            PA_CARDS_CATALOG[id] = {
              id,
              category: srvCard.category || "cabin",
              default_ttl: srvCard.default_ttl || 180,
              titles: srvCard.titles || { en: srvCard.title || id },
              bodies: srvCard.bodies || { en: srvCard.body || "" },
            };
          }
        }
      }

      if (Array.isArray(data.crew_responses)) {
        for (const srvReply of data.crew_responses) {
          const id = srvReply.id || srvReply.response_id;
          if (!id) continue;
          if (!CREW_RESPONSES_CATALOG[id]) {
            CREW_RESPONSES_CATALOG[id] = {
              id,
              labels: srvReply.labels || { en: id },
            };
          }
        }
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  // Local supplemental metadata store (for temperature, dietary, notes, crew replies across refreshes)
  function getLocalRequestMeta(requestId) {
    if (!requestId) return {};
    try {
      const raw = sessionStorage.getItem(STORAGE_KEYS.LOCAL_META);
      const map = raw ? JSON.parse(raw) : {};
      return map[requestId] || {};
    } catch (_) {
      return {};
    }
  }

  function saveLocalRequestMeta(requestId, patch) {
    if (!requestId || !patch) return;
    try {
      const raw = sessionStorage.getItem(STORAGE_KEYS.LOCAL_META);
      const map = raw ? JSON.parse(raw) : {};
      map[requestId] = Object.assign({}, map[requestId] || {}, patch);
      sessionStorage.setItem(STORAGE_KEYS.LOCAL_META, JSON.stringify(map));
    } catch (_) {}
  }

  // Web Audio API Synthesized Chimes (Offline Zero-Asset Audio)
  let sharedAudioCtx = null;

  function getAudioCtx() {
    if (typeof window === "undefined") return null;
    if (!sharedAudioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        sharedAudioCtx = new AudioContextClass();
      }
    }
    if (sharedAudioCtx && sharedAudioCtx.state === "suspended") {
      sharedAudioCtx.resume().catch(() => {});
    }
    return sharedAudioCtx;
  }

  function isSoundMuted() {
    try {
      return localStorage.getItem(STORAGE_KEYS.MUTED) === "1";
    } catch (_) {
      return false;
    }
  }

  function toggleSoundMute() {
    const next = !isSoundMuted();
    try {
      localStorage.setItem(STORAGE_KEYS.MUTED, next ? "1" : "0");
    } catch (_) {}
    if (!next) {
      playSoftTap();
    }
    return next;
  }

  function playCabinChime(type) {
    if (isSoundMuted()) return;
    try {
      const ctx = getAudioCtx();
      if (!ctx) return;
      const now = ctx.currentTime;
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(type === "urgent" ? 659.25 : 587.33, now);
      gain1.gain.setValueAtTime(0.14, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.75);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.75);

      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(type === "urgent" ? 523.25 : 440.0, now + 0.35);
      gain2.gain.setValueAtTime(0.14, now + 0.35);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 1.3);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.35);
      osc2.stop(now + 1.3);
    } catch (_) {}
  }

  function playServerAckChime() {
    if (isSoundMuted()) return;
    try {
      const ctx = getAudioCtx();
      if (!ctx) return;
      const now = ctx.currentTime;
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(523.25, now);
      gain1.gain.setValueAtTime(0.09, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.25);

      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(659.25, now + 0.12);
      gain2.gain.setValueAtTime(0.11, now + 0.12);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.12);
      osc2.stop(now + 0.55);
    } catch (_) {}
  }

  function playSoftTap() {
    if (isSoundMuted()) return;
    try {
      const ctx = getAudioCtx();
      if (!ctx) return;
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(420, now);
      osc.frequency.exponentialRampToValueAtTime(140, now + 0.045);
      gain.gain.setValueAtTime(0.05, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.045);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.045);
    } catch (_) {}
  }

  // Explicit user-triggered SpeechSynthesis TTS for Crew Replies
  function speakReplyText(text, langCode) {
    if (!text) return false;
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      showToast("Voice playback is not supported on this browser.", "error");
      return false;
    }
    try {
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      const langObj = SUPPORTED_LANGUAGES.find((l) => l.code === (langCode || getLang()));
      utter.lang = (langObj && langObj.speechLang) || "en-US";
      utter.rate = 0.96;
      window.speechSynthesis.speak(utter);
      return true;
    } catch (_) {
      return false;
    }
  }

  // Exact SVG Icons from SoraLink-UI-Figma-1/src/components/icons/RequestIcons.tsx (with #C8102E accents)
  function getCategoryIconSvg(intentId, size) {
    const s = size || 24;
    switch (intentId) {
      case "water_request":
        return `<svg width="${s}" height="${s}" viewBox="0 0 32 32" fill="none"><path d="M9 7H23L21 25C20.8 26.7 19.4 28 17.7 28H14.3C12.6 28 11.2 26.7 11 25L9 7Z" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/><path d="M10.2 15.5C12.5 14 14.5 17 16.5 15.5C18.5 14 20 16.2 21.8 15.5" stroke="#C8102E" stroke-width="1.75" stroke-linecap="round"/><path d="M16 19.5C16 19.5 14 21.8 14 23C14 24.1 14.9 25 16 25C17.1 25 18 24.1 18 23C18 21.8 16 19.5 16 19.5Z" fill="#C8102E" fill-opacity="0.18" stroke="#C8102E" stroke-width="1.4"/></svg>`;
      case "blanket_request":
        return `<svg width="${s}" height="${s}" viewBox="0 0 32 32" fill="none"><rect x="5" y="8" width="22" height="16" rx="3" stroke="currentColor" stroke-width="1.75"/><path d="M5 13.5H27" stroke="currentColor" stroke-width="1.5"/><path d="M5 18.5H27" stroke="currentColor" stroke-width="1.5"/><path d="M21 8V13.5" stroke="#C8102E" stroke-width="2" stroke-linecap="round"/><path d="M10 24V26.5M14 24V26.5M18 24V26.5M22 24V26.5" stroke="#C8102E" stroke-width="1.5" stroke-linecap="round"/></svg>`;
      case "pillow_request":
        return `<svg width="${s}" height="${s}" viewBox="0 0 32 32" fill="none"><path d="M6 10C6 8.34315 7.34315 7 9 7C12.5 8 19.5 8 23 7C24.6569 7 26 8.34315 26 10C25 13.5 25 18.5 26 22C26 23.6569 24.6569 25 23 25C19.5 24 12.5 24 9 25C7.34315 25 6 23.6569 6 22C7 18.5 7 13.5 6 10Z" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/><path d="M12 16C14.5 15 17.5 15 20 16" stroke="#C8102E" stroke-width="1.75" stroke-linecap="round"/></svg>`;
      case "accessibility_assist":
        return `<svg width="${s}" height="${s}" viewBox="0 0 32 32" fill="none"><circle cx="16" cy="7.5" r="2.5" stroke="#C8102E" stroke-width="1.75"/><path d="M10 13.5C13.5 14.8 18.5 14.8 22 13.5" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/><path d="M16 14.5V20.5" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/><path d="M13 26.5L16 20.5L19 26.5" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/><circle cx="16" cy="16.5" r="11.5" stroke="#C8102E" stroke-width="1.4" stroke-dasharray="3 2.5"/></svg>`;
      case "medical_help":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="15" rx="2.5"/><path d="M9 5V3.5A1.5 1.5 0 0 1 10.5 2h3A1.5 1.5 0 0 1 15 3.5V5"/><path d="M12 9.5v6" stroke="#C8102E"/><path d="M9 12.5h6" stroke="#C8102E"/></svg>`;
      case "motion_sickness":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a9 9 0 1 0 9 9"/><path d="M12 7a5 5 0 1 0 5 5"/><circle cx="12" cy="12" r="1.5" fill="#C8102E" stroke="#C8102E"/></svg>`;
      case "safety_concern":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 8v4" stroke="#C8102E"/><path d="M12 16h.01" stroke="#C8102E"/></svg>`;
      case "tea_coffee":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M17 8h1a4 4 0 1 1 0 8h-1"/><path d="M3 8h14v7a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V8z"/><line x1="6" y1="2" x2="6" y2="4" stroke="#C8102E"/><line x1="10" y1="2" x2="10" y2="4" stroke="#C8102E"/><line x1="14" y1="2" x2="14" y2="4" stroke="#C8102E"/></svg>`;
      case "meal_inquiry":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2v0a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>`;
      case "headphone_request":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/></svg>`;
      case "bag_help":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="7" width="16" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M8 7v13"/><path d="M16 7v13"/></svg>`;
      case "seat_issue":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M7 18v-6a5 5 0 1 1 10 0v6"/><path d="M5 18h14"/><path d="M6 21h12"/></svg>`;
      case "lavatory_assist":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="6" r="2"/><path d="M6 11h6l-1 9H7l-1-9Z"/><circle cx="17" cy="6" r="2"/><path d="M15 11h4v9h-4z"/></svg>`;
      case "customs_form":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>`;
      case "baby_care":
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9 10h.01"/><path d="M15 10h.01"/><path d="M9.5 15a3.5 3.5 0 0 0 5 0"/><path d="M12 3a2 2 0 0 1 2 2c0 1.1-.9 2-2 2"/></svg>`;
      default:
        return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>`;
    }
  }

  // Client-side multilingual keyword classifier fallback (when AI model is 503 or transcript edited)
  function classifyTextLocally(text) {
    const lower = (text || "").toLowerCase().trim();
    if (!lower) {
      return {
        outcome: "UNRELIABLE",
        intent_id: null,
        confidence: 0,
        attributes: {},
        alternatives: CANONICAL_INTENTS.slice(0, 4).map((i) => ({
          intent_id: i.id,
          label: i.labels.en,
          priority: i.priority,
          confidence: 0.25,
        })),
      };
    }

    const attributes = {};
    if (/warm|hot|白湯|お湯|温|熱|गुनगुना|गरम/.test(lower)) attributes.temperature = "WARM";
    else if (/cold|ice|chilled|冷|氷|冰|ठंडा/.test(lower)) attributes.temperature = "COLD";
    else if (/room|normal|常温|常溫|सामान्य/.test(lower)) attributes.temperature = "ROOM";

    if (/veg|vegetarian|素食|ベジタリアン|शाकाहारी|சைவம்/.test(lower)) attributes.dietary = "VEG";
    else if (/snack|light|軽食|點心|नाश्ता|सிற்றுண்டி/.test(lower)) attributes.dietary = "SNACK";

    const rules = [
      { id: "medical_help", re: /doctor|medical|pain|chest|faint|heart|emergency|sick|breath|医|急病|痛|苦しい|醫療|不舒服|डॉक्टर|दर्द|மருத்துவ/ },
      { id: "motion_sickness", re: /dizzy|nausea|vomit|motion|air\s*sick|酔|吐き気|めまい|暈|चक्कर|उल्टी|மயக்கம்/ },
      { id: "safety_concern", re: /smoke|fire|unsafe|hazard|danger|security|安全|煙|危険|危險|सुरक्षा|आग|பாதுகாப்பு/ },
      { id: "accessibility_assist", re: /wheelchair|accessibility|walk|blind|deaf|mobility|assist|介助|車椅子|お手伝い|無障礙|व्हीलचेयर|सहायता|உதவி/ },
      { id: "water_request", re: /water|thirsty|drink|hydration|水|お水|お湯|白湯|飲用水|पानी|प्यास|குடிநீர்|தண்ணீர்|पाणी/ },
      { id: "blanket_request", re: /blanket|cold|freezing|chilly|ブランケット|毛布|寒い|毛毯|कंबल|ठंड|போர்வை|ब्लँकेट/ },
      { id: "pillow_request", re: /pillow|neck|cushion|sleep|枕|まくら|クッション|枕頭|तकिया|தலையணை|उशी/ },
      { id: "tea_coffee", re: /tea|coffee|green tea|espresso|caffeine|お茶|緑茶|コーヒー|紅茶|茶|咖啡|चाय|कॉफी|தேநீர்|காபி|चहा/ },
      { id: "meal_inquiry", re: /meal|food|hungry|lunch|dinner|breakfast|snack|eat|食事|機内食|お腹|軽食|餐點|餓|भोजन|खाना|भूख|உணவு|जेवण/ },
      { id: "headphone_request", re: /headphone|earphone|earplug|audio|eye mask|ヘッドホン|イヤホン|耳機|हेडफोन|ஹெட்போன்/ },
      { id: "bag_help", re: /bag|luggage|suitcase|overhead|bin|carry-on|荷物|スーツケース|棚|行李|सामान|बैग|பைகள்/ },
      { id: "seat_issue", re: /seat|recline|screen|monitor|light|table|broken|座席|モニター|画面|テーブル|座位|螢幕|सीट|स्क्रीन|இருக்கை/ },
      { id: "lavatory_assist", re: /toilet|restroom|lavatory|bathroom|washroom|トイレ|化粧室|お手洗い|洗手間|शौचालय|वाशरूम|கழிப்பறை/ },
      { id: "customs_form", re: /customs|declaration|form|landing card|pen|immigration|税関|申告書|ペン|海關|筆|कस्टम|फॉर्म|पेन/ },
      { id: "baby_care", re: /baby|infant|diaper|milk|child|kid|stroller|赤ちゃん|ベビー|おむつ|ミルク|嬰兒|शिशु|बच्चा|குழந்தை|बाळ/ },
    ];

    const matched = [];
    for (const rule of rules) {
      if (rule.re.test(lower)) {
        matched.push(rule.id);
      }
    }

    if (matched.length === 1) {
      const topMeta = getIntentMeta(matched[0]);
      return {
        outcome: "SUGGESTED",
        intent_id: matched[0],
        confidence: 0.9,
        attributes,
        alternatives: [
          {
            intent_id: matched[0],
            label: topMeta.labels.en,
            priority: topMeta.priority,
            confidence: 0.9,
          },
        ],
      };
    }

    if (matched.length > 1) {
      return {
        outcome: "REQUIRES_CHOICE",
        intent_id: matched[0],
        confidence: 0.65,
        attributes,
        alternatives: matched.slice(0, 4).map((id, idx) => {
          const m = getIntentMeta(id);
          return {
            intent_id: id,
            label: m.labels.en,
            priority: m.priority,
            confidence: Number((0.7 - idx * 0.1).toFixed(2)),
          };
        }),
      };
    }

    return {
      outcome: "UNRELIABLE",
      intent_id: null,
      confidence: 0.2,
      attributes,
      alternatives: CANONICAL_INTENTS.slice(0, 6).map((m) => ({
        intent_id: m.id,
        label: m.labels.en,
        priority: m.priority,
        confidence: 0.2,
      })),
    };
  }

  // Toast Notification Helper
  function showToast(message, type) {
    let container = document.getElementById("soralink-toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "soralink-toast-container";
      container.className = "toast-container";
      container.setAttribute("aria-live", "polite");
      document.body.appendChild(container);
    }

    const item = document.createElement("div");
    item.className = "toast-item" + (type === "success" ? " success" : "");
    item.textContent = message;
    container.appendChild(item);

    setTimeout(() => {
      if (item.parentNode) {
        item.parentNode.removeChild(item);
      }
    }, 4200);
  }

  // Unified REST API Wrapper
  async function apiFetch(path, options) {
    const opts = Object.assign(
      {
        method: "GET",
        credentials: "same-origin",
        headers: {},
      },
      options || {}
    );

    if (opts.body && !(opts.body instanceof FormData) && typeof opts.body === "object") {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }

    try {
      const response = await fetch(path, opts);
      let json = null;
      try {
        json = await response.json();
      } catch (_) {}

      const ok = response.ok && json && json.ok !== false;
      const errorObj = (json && json.error) || {};
      return {
        ok,
        status: response.status,
        data: json && json.data !== undefined ? json.data : json,
        errorCode: errorObj.code || (response.status === 401 ? "UNAUTHENTICATED" : null),
        errorMessage:
          errorObj.message ||
          (response.status === 401
            ? "Session expired or not authenticated."
            : !ok
            ? `Request failed (HTTP ${response.status})`
            : null),
        isUnauthenticated: response.status === 401,
        isNetworkError: false,
      };
    } catch (err) {
      return {
        ok: false,
        status: 0,
        data: null,
        errorCode: "NETWORK_ERROR",
        errorMessage: "Unable to reach cabin server. Reconnecting over local Wi-Fi…",
        isUnauthenticated: false,
        isNetworkError: true,
      };
    }
  }

  // Update Header Connection Pill UI + Truthful Offline Banner (App.tsx)
  function updateConnectionBadge(state) {
    const pill = document.getElementById("header-conn-pill");
    const textEl = document.getElementById("header-conn-text");
    if (pill) {
      pill.classList.remove("connected", "reconnecting", "offline");
      if (state === "connected") {
        pill.classList.add("connected");
        if (textEl) textEl.textContent = t("connected");
      } else if (state === "reconnecting") {
        pill.classList.add("reconnecting");
        if (textEl) textEl.textContent = t("reconnecting");
      } else {
        pill.classList.add("offline");
        if (textEl) textEl.textContent = t("offline");
      }
    }

    let banner = document.getElementById("offline-banner-bar");
    if (state === "offline") {
      if (!banner) {
        const header = document.querySelector(".site-header");
        if (header && header.parentNode) {
          banner = document.createElement("div");
          banner.id = "offline-banner-bar";
          banner.className = "offline-banner-bar";
          banner.setAttribute("role", "status");
          header.parentNode.insertBefore(banner, header.nextSibling);
        }
      }
      if (banner) {
        banner.classList.remove("hidden");
        banner.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#C8102E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"/><path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/><path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/><path d="M10.71 5.05A16 16 0 0 1 22.58 9"/><path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg><span>Device is currently offline or disconnected from cabin server. Reconnecting over cabin Wi-Fi…</span>`;
      }
    } else if (banner) {
      banner.classList.add("hidden");
    }
  }

  // Socket.IO Manager with Automatic State Reconciliation
  function createSocketManager(handlers) {
    const callbacks = handlers || {};
    let socket = null;
    let isReconnecting = false;

    if (typeof window.io !== "function") {
      updateConnectionBadge("offline");
      return { socket: null, requestResync: () => {} };
    }

    updateConnectionBadge("reconnecting");

    socket = window.io({
      path: "/socket.io",
      transports: ["websocket", "polling"],
      withCredentials: true,
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 8000,
    });

    socket.on("connect", () => {
      updateConnectionBadge("connected");
      if (isReconnecting) {
        isReconnecting = false;
        socket.emit("request_resync", {});
        if (typeof callbacks.onResync === "function") {
          callbacks.onResync("socket_reconnected");
        }
      }
      if (typeof callbacks.onConnect === "function") {
        callbacks.onConnect();
      }
    });

    socket.on("connection_ready", (payload) => {
      updateConnectionBadge("connected");
      if (typeof callbacks.onConnectionReady === "function") {
        callbacks.onConnectionReady(payload || {});
      }
    });

    socket.on("disconnect", () => {
      isReconnecting = true;
      updateConnectionBadge("reconnecting");
      if (typeof callbacks.onDisconnect === "function") {
        callbacks.onDisconnect();
      }
    });

    socket.on("connect_error", () => {
      isReconnecting = true;
      updateConnectionBadge("offline");
    });

    socket.on("state_resync_required", (payload) => {
      if (typeof callbacks.onResync === "function") {
        callbacks.onResync((payload && payload.reason) || "state_resync_required");
      }
    });

    socket.on("request_created", (payload) => {
      if (typeof callbacks.onRequestCreated === "function") {
        callbacks.onRequestCreated(payload || {});
      }
    });

    socket.on("request_updated", (payload) => {
      if (typeof callbacks.onRequestUpdated === "function") {
        callbacks.onRequestUpdated(payload || {});
      }
    });

    socket.on("crew_reply", (payload) => {
      if (typeof callbacks.onCrewReply === "function") {
        callbacks.onCrewReply(payload || {});
      }
    });

    socket.on("follow_up_requested", (payload) => {
      if (typeof callbacks.onFollowUpRequested === "function") {
        callbacks.onFollowUpRequested(payload || {});
      }
    });

    socket.on("pa_broadcast_created", (payload) => {
      if (typeof callbacks.onPABroadcastCreated === "function") {
        callbacks.onPABroadcastCreated(payload || {});
      }
    });

    socket.on("pa_broadcast_ended", (payload) => {
      if (typeof callbacks.onPABroadcastEnded === "function") {
        callbacks.onPABroadcastEnded(payload || {});
      }
    });

    // Mobile wake / tab focus automatic reconciliation
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        if (socket && !socket.connected) {
          socket.connect();
        }
        if (typeof callbacks.onResync === "function") {
          callbacks.onResync("visibilitychange");
        }
      }
    });

    window.addEventListener("pageshow", () => {
      if (typeof callbacks.onResync === "function") {
        callbacks.onResync("pageshow");
      }
    });

    window.addEventListener("offline", () => updateConnectionBadge("offline"));
    window.addEventListener("online", () => {
      if (socket && socket.connected) updateConnectionBadge("connected");
    });

    return {
      socket,
      requestResync: () => {
        if (socket && socket.connected) {
          socket.emit("request_resync", {});
        }
        if (typeof callbacks.onResync === "function") {
          callbacks.onResync("manual_resync");
        }
      },
      disconnect: () => {
        if (socket) socket.disconnect();
      },
    };
  }

  // Format timestamp & countdown helpers
  function formatTimeHHMM(msOrSec) {
    if (!msOrSec) return "";
    const ms = msOrSec < 1e11 ? msOrSec * 1000 : msOrSec;
    const d = new Date(ms);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function formatCountdownMMSS(remainingMs) {
    const totalSec = Math.max(0, Math.ceil(remainingMs / 1000));
    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
  }

  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Bind common header controls (sound mute toggle, native select & custom Figma Globe/Check popover)
  function initHeaderControls(onLangChanged) {
    const langSelect = document.getElementById("header-lang-select");
    const langWrap = langSelect ? langSelect.closest(".lang-select-wrap") : null;

    if (langSelect) {
      langSelect.innerHTML = SUPPORTED_LANGUAGES.map(
        (l) => `<option value="${l.code}">${escapeHtml(l.label)}</option>`
      ).join("");
      langSelect.value = getLang();
      langSelect.addEventListener("change", (e) => {
        playSoftTap();
        setLang(e.target.value);
        renderPopoverState();
        if (typeof onLangChanged === "function") {
          onLangChanged(e.target.value);
        }
      });
    }

    // Inject custom Figma Globe/Check popover button & dropdown alongside native select
    let popoverMenu = null;
    let popoverBtnCodeEl = null;

    function renderPopoverState() {
      const current = getLang();
      if (langSelect && langSelect.value !== current) {
        langSelect.value = current;
      }
      if (popoverBtnCodeEl) {
        popoverBtnCodeEl.textContent = current.toUpperCase();
      }
      if (popoverMenu) {
        popoverMenu.innerHTML = `
          <div class="lang-popover-header">Language / 言語 / भाषा / மொழி</div>
          ${SUPPORTED_LANGUAGES.map((l) => {
            const isAct = l.code === current;
            return `
              <button type="button" class="lang-popover-item ${isAct ? "active" : ""}" data-popover-lang="${escapeHtml(l.code)}" role="option" aria-selected="${isAct}">
                <span>${escapeHtml(l.nativeName || l.label)}</span>
                ${
                  isAct
                    ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#C8102E" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
                    : `<span class="lang-popover-code">${escapeHtml(l.code)}</span>`
                }
              </button>
            `;
          }).join("")}
        `;
        popoverMenu.querySelectorAll("[data-popover-lang]").forEach((btn) => {
          btn.addEventListener("click", (ev) => {
            ev.stopPropagation();
            const chosen = btn.getAttribute("data-popover-lang");
            playSoftTap();
            setLang(chosen);
            popoverMenu.classList.add("hidden");
            renderPopoverState();
            if (typeof onLangChanged === "function") {
              onLangChanged(chosen);
            }
          });
        });
      }
    }

    if (langWrap && !langWrap.querySelector(".lang-popover-btn")) {
      // Keep native select accessible for automated tests while showing Figma Globe pill button
      langSelect.style.position = "absolute";
      langSelect.style.opacity = "0";
      langSelect.style.width = "1px";
      langSelect.style.height = "1px";
      langSelect.style.pointerEvents = "none";
      const oldChevron = langWrap.querySelector(".lang-select-chevron");
      if (oldChevron) oldChevron.style.display = "none";

      const popBtn = document.createElement("button");
      popBtn.type = "button";
      popBtn.className = "lang-popover-btn";
      popBtn.setAttribute("aria-label", "Select Language");
      popBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#C8102E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        <span class="lang-popover-btn-code">${escapeHtml(getLang().toUpperCase())}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      `;
      popoverBtnCodeEl = popBtn.querySelector(".lang-popover-btn-code");

      popoverMenu = document.createElement("div");
      popoverMenu.className = "lang-popover-menu hidden";
      popoverMenu.setAttribute("role", "listbox");

      langWrap.appendChild(popBtn);
      langWrap.appendChild(popoverMenu);
      renderPopoverState();

      popBtn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        playSoftTap();
        popoverMenu.classList.toggle("hidden");
      });

      document.addEventListener("click", (ev) => {
        if (popoverMenu && !langWrap.contains(ev.target)) {
          popoverMenu.classList.add("hidden");
        }
      });
    }

    const soundBtn = document.getElementById("header-sound-btn");
    const renderSoundIcon = () => {
      if (!soundBtn) return;
      const muted = isSoundMuted();
      soundBtn.classList.toggle("muted", muted);
      soundBtn.setAttribute("title", muted ? "Unmute Cabin Chimes" : "Mute Cabin Chimes");
      soundBtn.setAttribute("aria-label", muted ? "Unmute Cabin Chimes" : "Mute Cabin Chimes");
      soundBtn.innerHTML = muted
        ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>`
        : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>`;
    };
    renderSoundIcon();
    if (soundBtn) {
      soundBtn.addEventListener("click", () => {
        toggleSoundMute();
        renderSoundIcon();
      });
    }

    // Figma App.tsx navigation helpers & Alt+C / Ctrl+Shift+C shortcut
    window.navigateToCrew = () => {
      window.location.href = "/crew";
    };
    window.navigateToPassenger = () => {
      window.location.href = "/passenger";
    };
    document.addEventListener("keydown", (e) => {
      if ((e.altKey && e.key.toLowerCase() === "c") || (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "c")) {
        e.preventDefault();
        if (window.location.pathname.startsWith("/crew")) {
          window.location.href = "/passenger";
        } else {
          window.location.href = "/crew";
        }
      }
    });
  }

  window.SoraLink = {
    SUPPORTED_LANGUAGES,
    CANONICAL_INTENTS,
    PA_CARDS_CATALOG,
    CREW_RESPONSES_CATALOG,
    getLang,
    setLang,
    t,
    getIntentMeta,
    getIntentTitle,
    getIntentSubLabel,
    getIntentDescription,
    getPACardLocalized,
    getCrewResponseText,
    syncCatalogFromServer,
    getLocalRequestMeta,
    saveLocalRequestMeta,
    playCabinChime,
    playServerAckChime,
    playSoftTap,
    isSoundMuted,
    toggleSoundMute,
    speakReplyText,
    getCategoryIconSvg,
    classifyTextLocally,
    showToast,
    apiFetch,
    updateConnectionBadge,
    createSocketManager,
    formatTimeHHMM,
    formatCountdownMMSS,
    escapeHtml,
    initHeaderControls,
  };
})(window);
