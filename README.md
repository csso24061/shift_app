# 📄 シフト管理Webアプリ（MVP版）要件・設計書

> **概要:** 30分刻みのシフト作成、提出催促、労基法に準拠した給与の自動計算、期限付き変更申請を備えた、汎用シフト管理Webアプリの最小要件定義（MVP）および基本設計図集です。

---

## 📌 1. 簡易要件定義（システム要件）

### 🎯 目的
*   **汎用シフト管理:** 特定の業界に依存せず、30分刻みで誰でも直感的にシフト作成ができる。
*   **給与自動計算:** 労働時間に基づき、労基法に準拠した給与（残業・深夜手当）を自動計算する。
*   **プライバシー保護:** 給与や労働時間は「本人」と「店舗管理者」以外には非公開。

### ⚙️ 技術・運用上の制約
*   **プラットフォーム:** スマートフォン・PCブラウザで動作する**Webアプリ**として構築。
*   **入力単位:** 固定パターンではなく、**30分刻み**で自由な時間を選択可能。
*   **締め日管理:** シフトの提出締め日や給与締め日は、店舗管理者が任意にコントロール可能。

### 🙅 今回は作らない範囲（非目標）
*   タイムカード等のリアルタイム打刻、スタッフ同士の直接チャットやシフト交換。[cite: 4]
*   「他店舗への応援（ヘルプ）」などの掛け持ち管理（1スタッフ1店舗所属に限定）。[cite: 4]
*   シフト当日1週間前を過ぎた変更申請のシステム処理（1週間前以降は外部で連絡し、管理者が手動変更）。[cite: 4]

### 👥 利用者とシステムへの入出力[cite: 4]

| ロール（権限） | 主な入力（システムに送るもの） | 主な出力（返ってくるもの） |
| :--- | :--- | :--- |
| **全体運営者**[cite: 4] | 店舗の新規登録、店舗管理者の初期アカウント発行[cite: 4] | 登録店舗の一覧、契約状況確認[cite: 4] |
| **店舗管理者**<br>*(※1IDでスタッフ機能と兼任)*[cite: 4] | シフトの調整・確定、各スタッフの時給設定、締め日等の管理設定、スタッフからの変更申請の承認/却下[cite: 4] | 店舗全体のシフト表、全スタッフの労働・給与一覧、未提出者への催促バナー発信、変更申請の通知[cite: 4] |
| **一般スタッフ**[cite: 4] | 30分刻みの希望シフト提出、確定シフトに対する変更申請（1週間前まで）[cite: 4] | 自分＋他人の確定シフトカレンダー（※他人の給与は見えない）、自身の給与明細データ、未提出時の催促アラート[cite: 4] |

---

## 📐 2. 基本設計図集

### 🗺️ ① ユースケース図（役割と機能の相関）[cite: 4]

#### 【図の説明】
アプリを使う「3つの立場（アクター）」と、それぞれが実行できる操作（ユースケース）の関係図です。[cite: 4]
店舗管理者が、自身のシフトを提出する「労働者としての機能」と、全体のシフトを調整する「管理者としての機能」を1つのIDで行き来できる関係性を整理しています。[cite: 4]
また、シフトを確定すると自動的に給与が計算される関係（include）や、未提出のスタッフがログインしたときだけポップアップが出る関係（extend）を定義しています。[cite: 4]

```mermaid
flowchart TD
    subgraph Actors [アクター]
        Admin["👤 全体運営者"]
        Manager["👤 店舗管理者\n(店長・社員)"]
        Staff["👤 一般スタッフ\n(アルバイトなど)"]
    end

    subgraph SystemBoundary [シフト管理アプリ]
        UC_Login(("ログインする"))
        UC_ViewCalendar(("確定シフトを閲覧する"))
        UC_ViewSalary(("自身の給与/労働時間を確認する"))
        
        UC_ManageTenant(("店舗の登録・管理を行う"))
        UC_IssueManager(("店舗管理者アカウントを発行する"))

        UC_SubmitShift(("希望シフトを提出する\n(30分刻み)"))
        UC_RequestChange(("シフトの変更を申請する\n(当日1週間前まで)"))

        UC_AdjustShift(("シフトの調整・確定を行う"))
        UC_ApproveChange(("シフト変更申請を承認する"))
        UC_ManageStaff(("スタッフアカウントを管理する"))
        UC_ConfigStore(("締め日・提出期限を設定する"))
        
        UC_CalcSalary(("給与を自動計算する\n(一律労基法ルール)"))
        UC_ShowAlert(("提出催促ポップアップを画面表示する"))
    end

    Admin --> UC_ManageTenant & UC_IssueManager
    Manager --> UC_AdjustShift & UC_ApproveChange & UC_ManageStaff & UC_ConfigStore & UC_SubmitShift & UC_RequestChange & UC_ViewCalendar & UC_ViewSalary
    Staff --> UC_SubmitShift & UC_RequestChange & UC_ViewCalendar & UC_ViewSalary

    UC_SubmitShift -.->|"<<include>>"| UC_Login
    UC_AdjustShift -.->|"<<include>>"| UC_Login
    UC_ManageTenant -.->|"<<include>>"| UC_Login
    UC_AdjustShift ===>|"<<include>>"| UC_CalcSalary
    UC_ShowAlert -.->|"<<extend>>\n(未提出時に発火)"| UC_Login
    UC_ApproveChange -.->|"<<extend>>\n(承認時)"| UC_AdjustShift