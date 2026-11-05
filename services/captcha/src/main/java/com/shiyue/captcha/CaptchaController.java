package com.shiyue.captcha;

import cloud.tianai.captcha.application.ImageCaptchaApplication;
import cloud.tianai.captcha.application.vo.ImageCaptchaVO;
import cloud.tianai.captcha.common.response.ApiResponse;
import cloud.tianai.captcha.validator.common.model.dto.ImageCaptchaTrack;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
class CaptchaController {
    private final ImageCaptchaApplication application;

    CaptchaController(ImageCaptchaApplication application) {
        this.application = application;
    }

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/gen")
    ResponseEntity<ApiResponse<ImageCaptchaVO>> generate(@RequestParam(defaultValue = "ROTATE") String type) {
        if (!"ROTATE".equals(type)) {
            return ResponseEntity.badRequest().body(ApiResponse.of(400, "Only ROTATE is supported", null));
        }
        return ResponseEntity.ok(application.generateCaptcha("ROTATE"));
    }

    @PostMapping("/check")
    ResponseEntity<ApiResponse<?>> check(@RequestBody CheckRequest request) {
        if (request.id == null || !request.id.matches("ROTATE_[a-f0-9]{32}")) {
            return ResponseEntity.badRequest().body(ApiResponse.of(400, "Invalid challenge", null));
        }
        if (!validTrack(request.data)) {
            application.getCacheStore().getAndRemoveCache("captcha:" + request.id);
            return ResponseEntity.badRequest().body(ApiResponse.of(400, "Invalid track", null));
        }
        // The official browser SDK sends page coordinates. The track interceptor
        // checks displacement from the pointer-down origin, not page position.
        float originX = request.data.getTrackList().get(0).getX();
        float originY = request.data.getTrackList().get(0).getY();
        for (ImageCaptchaTrack.Track point : request.data.getTrackList()) {
            point.setX(point.getX() - originX);
            point.setY(point.getY() - originY);
        }
        ApiResponse<?> response = application.matching(request.id, request.data);
        if (response.isSuccess()) {
            return ResponseEntity.ok(ApiResponse.ofSuccess(Map.of("id", request.id)));
        }
        return ResponseEntity.ok(response);
    }

    private boolean validTrack(ImageCaptchaTrack track) {
        if (track == null || track.getBgImageWidth() == null || track.getBgImageHeight() == null
                || track.getBgImageWidth() < 1 || track.getBgImageWidth() > 10000
                || track.getBgImageHeight() < 1 || track.getBgImageHeight() > 10000
                || track.getStartTime() == null || track.getStopTime() == null
                || track.getStartTime() < 0 || track.getStopTime() < track.getStartTime()
                || track.getStopTime() - track.getStartTime() > 120000
                || track.getTrackList() == null || track.getTrackList().isEmpty()
                || track.getTrackList().size() > 1500) return false;
        for (ImageCaptchaTrack.Track point : track.getTrackList()) {
            if (point == null || point.getX() == null || point.getY() == null || point.getT() == null
                    || !Float.isFinite(point.getX()) || !Float.isFinite(point.getY()) || !Float.isFinite(point.getT())
                    || point.getType() == null || !java.util.Set.of("down", "move", "up").contains(point.getType())) return false;
        }
        return true;
    }

    public static class CheckRequest {
        public String id;
        public ImageCaptchaTrack data;
    }
}
