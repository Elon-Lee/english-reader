package com.shiyue.captcha;

import cloud.tianai.captcha.application.ImageCaptchaApplication;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "shiyue.captcha.secret=socket-test-secret-at-least-32-characters")
class CaptchaSocketTest {
    @Autowired TestRestTemplate http;
    @Autowired ImageCaptchaApplication application;

    @Test
    void generationAndMatchingWorkAcrossRealHttp() {
        matchingAtPageOffset(0, 0);
    }

    @Test
    void sdkPageCoordinatesWorkWithoutWeakeningAngleOrReplayChecks() {
        matchingAtPageOffset(496, 612);
        matchingAtPageOffset(180, 1340);
    }

    private void matchingAtPageOffset(int pageX, int pageY) {
        assertEquals(HttpStatus.OK, http.getForEntity("/health", JsonNode.class).getStatusCode());
        assertEquals(HttpStatus.UNAUTHORIZED, http.getForEntity("/gen?type=ROTATE", JsonNode.class).getStatusCode());
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Captcha-Secret", "socket-test-secret-at-least-32-characters");
        headers.setContentType(MediaType.APPLICATION_JSON);
        ResponseEntity<JsonNode> generated = http.exchange("/gen?type=ROTATE", HttpMethod.GET, new HttpEntity<>(headers), JsonNode.class);
        assertEquals(HttpStatus.OK, generated.getStatusCode());
        JsonNode challenge = generated.getBody().path("data");
        String id = challenge.path("id").asText();
        assertTrue(id.startsWith("ROTATE_"));
        assertTrue(challenge.path("backgroundImage").asText().startsWith("data:image/"));
        float percentage = application.getCacheStore().getCache("captcha:" + id).getFloat("percentage");
        List<Map<String, Object>> points = new ArrayList<>();
        for (int i = 0; i < 20; i++) {
            points.add(Map.of("x", pageX + percentage * 242 * i / 19, "y", pageY + i % 3, "t", i * i * 3,
                    "type", i == 0 ? "down" : i == 19 ? "up" : "move"));
        }
        Map<String, Object> body = Map.of("id", id, "data", Map.of("bgImageWidth", 242, "bgImageHeight", 180,
                "startTime", 1000, "stopTime", 2200, "trackList", points));
        HttpEntity<?> request = new HttpEntity<>(body, headers);
        ResponseEntity<JsonNode> checked = http.postForEntity("/check", request, JsonNode.class);
        assertEquals(HttpStatus.OK, checked.getStatusCode());
        assertEquals(200, checked.getBody().path("code").asInt());
        assertTrue(checked.getBody().path("success").asBoolean());
        assertEquals(id, checked.getBody().path("data").path("id").asText());
        assertFalse(http.postForEntity("/check", request, JsonNode.class).getBody().path("success").asBoolean());
    }
}
