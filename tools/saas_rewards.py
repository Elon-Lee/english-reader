#!/usr/bin/env python3
"""Growth points, check-ins, redemption and invitation milestones."""
from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

from saas_auth import SaaSError, SaaSService, new_id, utcnow
from saas_membership import FEATURES, MembershipService, as_json, timestamp, can_watch_hd_video
from saas_journey import learning_milestone


MONTHLY_GROWTH_CAP = 100
RETIRED_REWARD_FEATURES = {'official_unlocks', 'mp3_imports', 'video_imports', 'youtube_imports'}
AI_REWARD_FEATURES = {'ai_context_generations', 'ai_grammar_generations'}


def local_day(timezone_name: str, at: datetime | None = None) -> date:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Asia/Shanghai")
    return (at or utcnow()).astimezone(zone).date()


class RewardService:
    def __init__(self, accounts: SaaSService, memberships: MembershipService):
        self.accounts, self.memberships = accounts, memberships

    def _user(self, cursor: Any, user_id: str) -> dict[str, Any]:
        cursor.execute("SELECT inviter_id FROM member_invites WHERE invitee_id=%s", (user_id,))
        invite = self.accounts._one(cursor)
        recipients = {user_id, str(invite["inviter_id"])} if invite else {user_id}
        for recipient in sorted(recipients):
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"growth-award:{recipient}",))
        cursor.execute("SELECT id,timezone,status FROM users WHERE id=%s FOR UPDATE", (user_id,))
        user = self.accounts._one(cursor)
        if not user or user["status"] != "active":
            raise SaaSError("account_unavailable", "账号不可用。", 403)
        return user

    def _month_key(self, day: date) -> str:
        return day.strftime("%Y-%m")

    def _balances(self, cursor: Any, user_id: str, month: str | None = None) -> dict[str, int]:
        if month:
            cursor.execute("SELECT COALESCE(SUM(GREATEST(points,0)),0) AS earned FROM reward_ledger WHERE user_id=%s AND month_key=%s", (user_id, month))
            earned = int((self.accounts._one(cursor) or {"earned": 0})["earned"])
        else: earned = 0
        cursor.execute("SELECT COALESCE(SUM(points),0) AS balance FROM reward_ledger WHERE user_id=%s", (user_id,))
        balance = int((self.accounts._one(cursor) or {"balance": 0})["balance"])
        return {"balance": balance, "monthEarned": earned, "monthCap": MONTHLY_GROWTH_CAP}

    def _award(self, cursor: Any, user_id: str, event_type: str, event_key: str, points: int, day: date, metadata: dict[str, Any] | None = None) -> int:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"growth-award:{user_id}",))
        cursor.execute("SELECT points FROM reward_ledger WHERE user_id=%s AND event_type=%s AND event_key=%s", (user_id, event_type, event_key))
        existing = self.accounts._one(cursor)
        if existing: return 0
        month = self._month_key(day)
        balance = self._balances(cursor, user_id, month)
        granted = max(0, min(int(points), balance["monthCap"] - balance["monthEarned"]))
        cursor.execute(
            """INSERT INTO reward_ledger(id,user_id,month_key,reward_day,event_type,event_key,points,metadata_json)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            (new_id(), user_id, month, day, event_type, event_key, granted, json.dumps(metadata or {})),
        )
        return granted

    def _streak(self, cursor: Any, user_id: str, day: date) -> int:
        cursor.execute("SELECT checkin_day FROM checkins WHERE user_id=%s AND checkin_day<=%s ORDER BY checkin_day DESC", (user_id, day))
        expected, count = day, 0
        for row in self.accounts._many(cursor):
            found = row["checkin_day"]
            if found != expected: break
            count += 1; expected -= timedelta(days=1)
        return count

    def _makeup_card(self, cursor: Any, user_id: str) -> dict[str, Any] | None:
        cursor.execute(
            """SELECT rr.* FROM reward_redemptions rr JOIN reward_catalog rc ON rc.id=rr.reward_catalog_id
            WHERE rr.user_id=%s AND rr.status='active' AND rc.reward_type='makeup_card' ORDER BY rr.created_at FOR UPDATE SKIP LOCKED LIMIT 1""",
            (user_id,),
        )
        return self.accounts._one(cursor)

    def checkin(self, user_id: str, requested_day: Any = None) -> dict[str, Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user = self._user(cursor, user_id);today=local_day(user["timezone"])
                if requested_day in (None, ""): target=today
                else:
                    try: target=date.fromisoformat(str(requested_day))
                    except ValueError as exc: raise SaaSError("invalid_checkin_day", "补签日期无效。", 400) from exc
                if target > today: raise SaaSError("invalid_checkin_day", "不能签到未来日期。", 400)
                cursor.execute("SELECT id FROM checkins WHERE user_id=%s AND checkin_day=%s", (user_id, target))
                if cursor.fetchone(): raise SaaSError("already_checked_in", "当天已经签到，不能重复领取成长值。", 409)
                kind, card = "regular", None
                if target < today:
                    card=self._makeup_card(cursor,user_id)
                    if not card: raise SaaSError("makeup_card_required", "补签需要一张补签卡。", 409)
                    kind="makeup";cursor.execute("UPDATE reward_redemptions SET status='used',used_at=NOW() WHERE id=%s",(card["id"],))
                cursor.execute("INSERT INTO checkins(id,user_id,checkin_day,timezone,kind,makeup_redemption_id) VALUES(%s,%s,%s,%s,%s,%s)",(new_id(),user_id,target,user["timezone"],kind,card["id"] if card else None))
                streak=self._streak(cursor,user_id,target);cursor.execute("UPDATE checkins SET streak_count=%s WHERE user_id=%s AND checkin_day=%s",(streak,user_id,target))
                granted=self._award(cursor,user_id,"checkin",target.isoformat(),1,target,{"kind":kind,"streak":streak})
                bonus=0
                for threshold,points in ((3,2),(7,5),(14,10),(30,20)):
                    if streak==threshold: bonus=self._award(cursor,user_id,"streak",f"{target.isoformat()}:{threshold}",points,target,{"streak":streak});break
                return {"status":"checked_in","day":target.isoformat(),"kind":kind,"streak":streak,"pointsGranted":granted+bonus,"checkinPoints":granted,"streakPoints":bonus,"statusInfo":self._status(cursor,user_id,user)}

    def activity(self, user_id: str, reading_seconds: Any, sentences: Any, reviews: Any, idempotency_key: str) -> dict[str, Any]:
        try: seconds=max(0,min(86_400,int(float(reading_seconds or 0))));sentence_count=max(0,min(10_000,int(sentences or 0)));review_count=max(0,min(10_000,int(reviews or 0)))
        except (ValueError,TypeError) as exc: raise SaaSError("invalid_activity", "学习活动数据无效。", 400) from exc
        key=str(idempotency_key or "").strip()
        if not key or len(key)>255: raise SaaSError("invalid_idempotency_key", "操作标识无效。", 400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user=self._user(cursor,user_id);day=local_day(user["timezone"])
                cursor.execute("INSERT INTO reward_activity_events(id,user_id,idempotency_key,activity_day,reading_seconds,sentences,reviews) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (user_id,idempotency_key) DO NOTHING RETURNING id",(new_id(),user_id,key,day,seconds,sentence_count,review_count))
                if not cursor.fetchone(): return {"idempotent":True,"statusInfo":self._status(cursor,user_id,user)}
                if seconds>0:
                    learning_milestone(cursor,user_id,"first_reading")
                cursor.execute("""INSERT INTO reward_daily_activity(user_id,activity_day,timezone,reading_seconds,sentences,reviews)
                VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT (user_id,activity_day) DO UPDATE SET reading_seconds=reward_daily_activity.reading_seconds+EXCLUDED.reading_seconds,sentences=reward_daily_activity.sentences+EXCLUDED.sentences,reviews=reward_daily_activity.reviews+EXCLUDED.reviews,updated_at=NOW() RETURNING *""",(user_id,day,user["timezone"],seconds,sentence_count,review_count))
                activity=self.accounts._one(cursor) or {};points=0
                if not activity["valid_reading_awarded"] and int(activity["reading_seconds"])>=600 and int(activity["sentences"])>=5:
                    cursor.execute("UPDATE reward_daily_activity SET valid_reading_awarded=TRUE WHERE user_id=%s AND activity_day=%s",(user_id,day));points+=self._award(cursor,user_id,"valid_reading",day.isoformat(),2,day,{"readingSeconds":activity["reading_seconds"],"sentences":activity["sentences"]});self._on_effective_learning(cursor,user_id,day)
                if not activity["review_awarded"] and int(activity["reviews"])>0:
                    cursor.execute("UPDATE reward_daily_activity SET review_awarded=TRUE WHERE user_id=%s AND activity_day=%s",(user_id,day));points+=self._award(cursor,user_id,"review",day.isoformat(),2,day,{"reviews":activity["reviews"]})
                return {"idempotent":False,"pointsGranted":points,"activity":{"day":day.isoformat(),"readingSeconds":int(activity["reading_seconds"]),"sentences":int(activity["sentences"]),"reviews":int(activity["reviews"])},"statusInfo":self._status(cursor,user_id,user)}

    def complete_book(self,user_id:str,catalog_book_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user=self._user(cursor,user_id);day=local_day(user["timezone"])
                cursor.execute("SELECT 1 FROM user_library WHERE user_id=%s AND catalog_book_id=%s",(user_id,catalog_book_id))
                if not cursor.fetchone():raise SaaSError("catalog_book_locked","请先将读物加入书架后再标记完成。",403)
                cursor.execute("SELECT reading_seconds FROM reward_daily_activity WHERE user_id=%s AND activity_day=%s",(user_id,day));activity=self.accounts._one(cursor)
                if not activity or int(activity["reading_seconds"] or 0)<60:raise SaaSError("reading_time_insufficient","阅读满 1 分钟并到达正文底部后才会自动记录完成。",409)
                granted=self._award(cursor,user_id,"official_book_completed",catalog_book_id,10,day,{"catalogBookId":catalog_book_id})
                return {"status":"recorded","pointsGranted":granted,"statusInfo":self._status(cursor,user_id,user)}

    def _credit_feature(self,cursor:Any,user_id:str,feature:str,quantity:int,redemption_id:str)->None:
        if feature not in FEATURES:raise SaaSError("invalid_reward","奖励权益无效。",400)
        context=self.memberships._context(cursor,user_id)
        context=self.memberships._quota_context(cursor,context,feature)
        cursor.execute("""INSERT INTO usage_ledger(id,user_id,usage_period_id,feature,quantity,reason,idempotency_key,metadata_json)
        VALUES(%s,%s,%s,%s,%s,'credit',%s,%s::jsonb) ON CONFLICT DO NOTHING""",(new_id(),user_id,context["period"]["id"],feature,-quantity,f"reward:{redemption_id}",json.dumps({"rewardRedemptionId":redemption_id})))

    def redeem(self,user_id:str,code:str,idempotency_key:str)->dict[str,Any]:
        key=str(idempotency_key or "").strip();code=str(code or "").strip()
        if not key:raise SaaSError("invalid_idempotency_key","操作标识无效。",400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user=self._user(cursor,user_id);day=local_day(user["timezone"])
                cursor.execute("SELECT rr.*,rc.code,rc.title,rc.reward_type,rc.feature,rc.quantity FROM reward_redemptions rr JOIN reward_catalog rc ON rc.id=rr.reward_catalog_id WHERE rr.user_id=%s AND rr.idempotency_key=%s FOR UPDATE",(user_id,key));existing=self.accounts._one(cursor)
                if existing:return {"redemption":self._redemption(existing),"idempotent":True,"statusInfo":self._status(cursor,user_id,user)}
                cursor.execute("SELECT * FROM reward_catalog WHERE code=%s AND active=TRUE",(code,));reward=self.accounts._one(cursor)
                if not reward:raise SaaSError("reward_not_found","奖励不存在或已下架。",404)
                if reward['feature'] in RETIRED_REWARD_FEATURES:
                    raise SaaSError('reward_unavailable', '该奖励已停止兑换，你的成长值不会扣除。', 409)
                if reward['feature'] in AI_REWARD_FEATURES and can_watch_hd_video(cursor, user_id):
                    raise SaaSError('reward_unnecessary', '当前会员已包含不限次 AI 分析，无需兑换次数。', 409)
                balance=self._balances(cursor,user_id)
                if balance["balance"]<int(reward["cost_points"]):raise SaaSError("insufficient_growth_points","成长值不足。",409,{"balance":balance["balance"],"required":int(reward["cost_points"])})
                redemption_id=new_id();cursor.execute("INSERT INTO reward_redemptions(id,user_id,reward_catalog_id,cost_points,idempotency_key) VALUES(%s,%s,%s,%s,%s)",(redemption_id,user_id,reward["id"],reward["cost_points"],key))
                cursor.execute("INSERT INTO reward_ledger(id,user_id,month_key,reward_day,event_type,event_key,points,metadata_json) VALUES(%s,%s,%s,%s,'redemption',%s,%s,%s::jsonb)",(new_id(),user_id,self._month_key(day),day,redemption_id,-int(reward["cost_points"]),json.dumps({"code":reward["code"]})))
                if reward["reward_type"]=="quota_credit":self._credit_feature(cursor,user_id,reward["feature"],int(reward["quantity"]),redemption_id)
                cursor.execute("SELECT rr.*,rc.code,rc.title,rc.reward_type,rc.feature,rc.quantity FROM reward_redemptions rr JOIN reward_catalog rc ON rc.id=rr.reward_catalog_id WHERE rr.id=%s",(redemption_id,));created=self.accounts._one(cursor)
                return {"redemption":self._redemption(created or {}),"idempotent":False,"statusInfo":self._status(cursor,user_id,user)}

    def _fraud_blocked(self,cursor:Any,invite:dict[str,Any])->bool:
        if not invite.get("invitee_id") or invite["inviter_id"]==invite["invitee_id"]:return True
        cursor.execute("""SELECT EXISTS(SELECT 1 FROM devices a JOIN devices b ON a.device_key=b.device_key
        WHERE a.user_id=%s AND b.user_id=%s) AS shared""",(invite["inviter_id"],invite["invitee_id"]))
        if bool((self.accounts._one(cursor)or{"shared":False})["shared"]):return True
        cursor.execute("""SELECT EXISTS(SELECT 1 FROM invitation_uses a JOIN invitation_uses b ON a.ip_address=b.ip_address
        WHERE a.user_id=%s AND b.user_id=%s AND a.ip_address<>'') AS shared""",(invite["inviter_id"],invite["invitee_id"]))
        return bool((self.accounts._one(cursor)or{"shared":False})["shared"])

    def _on_effective_learning(self,cursor:Any,invitee_id:str,day:date)->None:
        cursor.execute("SELECT * FROM member_invites WHERE invitee_id=%s FOR UPDATE",(invitee_id,));invite=self.accounts._one(cursor)
        if not invite:return
        blocked=self._fraud_blocked(cursor,invite);cursor.execute("INSERT INTO member_invite_rewards(id,member_invite_id,reward_type,points,fraud_blocked) VALUES(%s,%s,'effective_learning',10,%s) ON CONFLICT DO NOTHING RETURNING id",(new_id(),invite["id"],blocked))
        if cursor.fetchone() and not blocked:self._award(cursor,invite["inviter_id"],"member_invite_effective",invite["id"],10,day,{"inviteeId":invitee_id})
        cursor.execute("UPDATE member_invites SET status=CASE WHEN status='paid' THEN status ELSE 'effective_learning' END,effective_learning_at=COALESCE(effective_learning_at,NOW()) WHERE id=%s",(invite["id"],))

    def on_first_paid(self,user_id:str)->None:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user=self._user(cursor,user_id);context=self.memberships._context(cursor,user_id)
                if int(context["plan"]["rank"])<1:return
                cursor.execute("SELECT * FROM member_invites WHERE invitee_id=%s FOR UPDATE",(user_id,));invite=self.accounts._one(cursor)
                if not invite:return
                day=local_day(user["timezone"]);blocked=self._fraud_blocked(cursor,invite);cursor.execute("INSERT INTO member_invite_rewards(id,member_invite_id,reward_type,points,fraud_blocked) VALUES(%s,%s,'first_paid',30,%s) ON CONFLICT DO NOTHING RETURNING id",(new_id(),invite["id"],blocked))
                if cursor.fetchone() and not blocked:self._award(cursor,invite["inviter_id"],"member_invite_paid",invite["id"],30,day,{"inviteeId":user_id})
                cursor.execute("UPDATE member_invites SET status='paid',first_paid_at=COALESCE(first_paid_at,NOW()) WHERE id=%s",(invite["id"],))

    def issue_invite(self,user_id:str,idempotency_key:str|None=None)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user=self._user(cursor,user_id);context=self.memberships._context(cursor,user_id)
                if idempotency_key:
                    key,prior=self.memberships._operation(cursor,user_id,user_id,"issue_member_invite",{},idempotency_key)
                    if prior:return {**prior,"idempotent":True}
                if int(context["plan"]["rank"])<1:raise SaaSError("invite_not_available","当前套餐没有邀请名额，请升级或等待活动发放。",403)
                cursor.execute("""SELECT * FROM member_invite_allowances WHERE user_id=%s AND quantity_remaining>0
                AND (expires_at IS NULL OR expires_at>NOW()) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1""",(user_id,))
                allowance=self.accounts._one(cursor)
                if not allowance:raise SaaSError("invite_not_available","当前没有可用邀请码额度，请等待后台或活动发放。",403)
                for _ in range(5):
                    code="MEM-"+secrets.token_urlsafe(8).replace("-","").replace("_","").upper()[:10]
                    cursor.execute("SELECT 1 FROM invitations WHERE code=%s",(code,))
                    if not cursor.fetchone():break
                else:raise RuntimeError("unable to create invitation code")
                invitation_id,member_id,batch_id=new_id(),new_id(),"invite-batch-"+new_id();cursor.execute("UPDATE member_invite_allowances SET quantity_remaining=quantity_remaining-1 WHERE id=%s",(allowance["id"],));cursor.execute("INSERT INTO invitation_batches(id,requested_count,max_uses,created_by,note,channel) VALUES(%s,1,1,%s,'会员邀请','member')",(batch_id,user_id));cursor.execute("INSERT INTO invitations(id,code,max_uses,created_by,note,channel,batch_id) VALUES(%s,%s,1,%s,'会员邀请','member',%s)",(invitation_id,code,user_id,batch_id));cursor.execute("INSERT INTO member_invites(id,inviter_id,invitation_id) VALUES(%s,%s,%s)",(member_id,user_id,invitation_id))
                result={"id":member_id,"code":code,"status":"active","idempotent":False}
                if idempotency_key:self.memberships._save_operation(cursor,user_id,user_id,"issue_member_invite",key,{},result)
                return result

    def status(self,user_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                user=self._user(cursor,user_id);return self._status(cursor,user_id,user)

    def _status(self,cursor:Any,user_id:str,user:dict[str,Any])->dict[str,Any]:
        today=local_day(user["timezone"]);balances=self._balances(cursor,user_id,self._month_key(today));cursor.execute("SELECT streak_count,kind FROM checkins WHERE user_id=%s AND checkin_day=%s",(user_id,today));checkin=self.accounts._one(cursor)
        cursor.execute("SELECT COUNT(*) AS total FROM reward_redemptions rr JOIN reward_catalog rc ON rc.id=rr.reward_catalog_id WHERE rr.user_id=%s AND rr.status='active' AND rc.reward_type='makeup_card'",(user_id,));cards=int((self.accounts._one(cursor)or{"total":0})["total"])
        cursor.execute("SELECT COALESCE(SUM(quantity_remaining),0) AS total FROM member_invite_allowances WHERE user_id=%s AND (expires_at IS NULL OR expires_at>NOW())",(user_id,));invite_allowance=int((self.accounts._one(cursor)or{"total":0})["total"])
        cursor.execute("SELECT mi.id,i.code,mi.status,mi.invitee_id FROM member_invites mi JOIN invitations i ON i.id=mi.invitation_id WHERE mi.inviter_id=%s ORDER BY mi.created_at DESC",(user_id,));invites=[{"id":row["id"],"code":row["code"],"status":row["status"],"inviteeId":row["invitee_id"]} for row in self.accounts._many(cursor)]
        return {"today":today.isoformat(),"timezone":user["timezone"],"checkedIn":bool(checkin),"streak":int(checkin["streak_count"]) if checkin else 0,"checkinKind":checkin["kind"] if checkin else None,"makeupCards":cards,"inviteAllowance":invite_allowance,"invites":invites,**balances}

    def catalog(self,user_id:str|None=None)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM reward_catalog WHERE active=TRUE ORDER BY sort_order,code")
                rows = self.accounts._many(cursor)
                paid = can_watch_hd_video(cursor, user_id) if user_id else False
                return {"rewards":[{"code":row["code"],"title":row["title"],"description":'仅增加兑换当日的 AI 可用次数。' if row['feature'] in AI_REWARD_FEATURES else row["description"],"costPoints":int(row["cost_points"]),"rewardType":row["reward_type"],"feature":row["feature"],"quantity":int(row["quantity"])} for row in rows if row['feature'] not in RETIRED_REWARD_FEATURES and not (paid and row['feature'] in AI_REWARD_FEATURES)]}

    def ledger(self,user_id:str,limit:int=100)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self._user(cursor,user_id);cursor.execute("SELECT * FROM reward_ledger WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",(user_id,max(1,min(200,int(limit)))))
                return {"items":[{"id":row["id"],"day":row["reward_day"].isoformat() if row["reward_day"] else None,"eventType":row["event_type"],"points":int(row["points"]),"createdAt":timestamp(row["created_at"])} for row in self.accounts._many(cursor)]}

    @staticmethod
    def _redemption(row:dict[str,Any])->dict[str,Any]:
        return {"id":row["id"],"code":row["code"],"title":row["title"],"status":row["status"],"costPoints":int(row["cost_points"]),"rewardType":row["reward_type"],"feature":row["feature"],"quantity":int(row["quantity"]),"createdAt":timestamp(row.get("created_at"))}
