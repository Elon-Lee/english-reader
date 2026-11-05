package com.shiyue.captcha;

import cloud.tianai.captcha.common.response.ApiResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.http.converter.HttpMessageNotReadableException;

@RestControllerAdvice
class ApiErrors {
    @ExceptionHandler({IllegalArgumentException.class, HttpMessageNotReadableException.class})
    ResponseEntity<ApiResponse<?>> invalidRequest(Exception ignored) {
        return ResponseEntity.badRequest().body(ApiResponse.of(400, "Invalid request", null));
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiResponse<?>> unavailable(Exception ignored) {
        return ResponseEntity.status(503).body(ApiResponse.of(503, "Captcha unavailable", null));
    }
}
