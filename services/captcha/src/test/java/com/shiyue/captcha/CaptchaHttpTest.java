package com.shiyue.captcha;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import cloud.tianai.captcha.application.ImageCaptchaApplication;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = {"shiyue.captcha.secret=test-only-secret-with-at-least-32-characters"})
@AutoConfigureMockMvc
class CaptchaHttpTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @Autowired ImageCaptchaApplication application;
    private static final String SECRET = "test-only-secret-with-at-least-32-characters";

    @Test
    void generationRequiresInternalSecret() throws Exception {
        mvc.perform(get("/gen").param("type", "ROTATE")).andExpect(status().isUnauthorized());
        mvc.perform(get("/gen;ignored").param("type", "ROTATE")).andExpect(status().isUnauthorized());
    }

    @Test
    void healthIsSafeAndDoesNotNeedASecret() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void generationUsesOfflineImagesAndOnlyRotate() throws Exception {
        JsonNode challenge = generate();
        assertEquals("ROTATE", challenge.path("type").asText());
        assertTrue(challenge.path("backgroundImage").asText().startsWith("data:image/"));
        assertTrue(challenge.path("templateImage").asText().startsWith("data:image/"));
        mvc.perform(get("/gen").param("type", "SLIDER").header("X-Captcha-Secret", SECRET))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.success").value(false));
    }

    @Test
    void realMatchingAcceptsCorrectTrackOnceAndRejectsReplay() throws Exception {
        String id = generate().path("id").asText();
        float percentage = application.getCacheStore().getCache("captcha:" + id).getFloat("percentage");
        String body = trackBody(id, percentage);
        mvc.perform(post("/check").header("X-Captcha-Secret", SECRET).contentType("application/json").content(body))
                .andExpect(status().isOk()).andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.success").value(true)).andExpect(jsonPath("$.data.id").value(id));
        mvc.perform(post("/check").header("X-Captcha-Secret", SECRET).contentType("application/json").content(body))
                .andExpect(status().isOk()).andExpect(jsonPath("$.success").value(false));
    }

    @Test
    void expiredChallengeAndWrongTrackCannotPass() throws Exception {
        String expiredId = generate().path("id").asText();
        var cache = application.getCacheStore();
        var answer = cache.getAndRemoveCache("captcha:" + expiredId);
        cache.setCache("captcha:" + expiredId, answer, 1L, java.util.concurrent.TimeUnit.MILLISECONDS);
        Thread.sleep(20);
        mvc.perform(post("/check").header("X-Captcha-Secret", SECRET).contentType("application/json")
                        .content(trackBody(expiredId, answer.getFloat("percentage"))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.success").value(false));
        String id = generate().path("id").asText();
        mvc.perform(post("/check").header("X-Captcha-Secret", SECRET).contentType("application/json").content(trackBody(id, -1)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.success").value(false));
    }

    @Test
    void checkRejectsMissingSecretInvalidDataAndOversizedBody() throws Exception {
        mvc.perform(post("/check").contentType("application/json").content("{}"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/check").header("X-Captcha-Secret", SECRET).contentType("application/json").content("{}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.success").value(false));
        mvc.perform(post("/check").header("X-Captcha-Secret", SECRET).contentType("application/json").content("x".repeat(65537)))
                .andExpect(status().isPayloadTooLarge()).andExpect(jsonPath("$.success").value(false));
    }

    private JsonNode generate() throws Exception {
        String body = mvc.perform(get("/gen").param("type", "ROTATE").header("X-Captcha-Secret", SECRET))
                .andExpect(status().isOk()).andExpect(jsonPath("$.success").value(true))
                .andReturn().getResponse().getContentAsString();
        return mapper.readTree(body).path("data");
    }

    private String trackBody(String id, float percentage) throws Exception {
        List<Map<String, Object>> tracks = new ArrayList<>();
        for (int i = 0; i < 20; i++) {
            tracks.add(Map.of("x", percentage * 242 * i / 19, "y", i % 3, "t", i * i * 3, "type", i == 0 ? "down" : i == 19 ? "up" : "move"));
        }
        return mapper.writeValueAsString(Map.of("id", id, "data", Map.of(
                "bgImageWidth", 242, "bgImageHeight", 180, "startTime", 1000, "stopTime", 2200, "trackList", tracks)));
    }
}
