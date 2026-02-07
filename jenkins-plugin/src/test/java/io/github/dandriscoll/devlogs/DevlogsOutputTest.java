package io.github.dandriscoll.devlogs;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition;
import org.jenkinsci.plugins.workflow.job.WorkflowJob;
import org.jenkinsci.plugins.workflow.job.WorkflowRun;
import org.junit.After;
import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.jvnet.hudson.test.JenkinsRule;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.Assert.*;

/**
 * Tests that verify the JSON payloads sent by the devlogs plugin.
 */
public class DevlogsOutputTest {

    @Rule
    public JenkinsRule jenkins = new JenkinsRule();

    private MockWebServer mockServer;
    private String mockUrl;
    private final Gson gson = new Gson();

    @Before
    public void setUp() throws Exception {
        mockServer = new MockWebServer();
        mockServer.start();
        // Use token@host format so the plugin detects collector mode
        mockUrl = "http://testtoken@" + mockServer.getHostName() + ":" + mockServer.getPort();
    }

    @After
    public void tearDown() throws Exception {
        mockServer.shutdown();
    }

    /**
     * Enqueue enough 200 responses and then drain all recorded requests,
     * parsing the collector JSON payloads into a flat list of record objects.
     */
    private List<JsonObject> collectRecords() throws Exception {
        List<JsonObject> records = new ArrayList<>();
        // Drain all requests that arrived - use longer timeout for the first
        // request and shorter for subsequent ones
        RecordedRequest req;
        while ((req = mockServer.takeRequest(5, TimeUnit.SECONDS)) != null) {
            String body = req.getBody().readUtf8();
            if (body.isEmpty()) continue;
            try {
                JsonObject payload = gson.fromJson(body, JsonObject.class);
                if (payload.has("records")) {
                    JsonArray arr = payload.getAsJsonArray("records");
                    for (JsonElement el : arr) {
                        records.add(el.getAsJsonObject());
                    }
                }
            } catch (Exception e) {
                // skip non-JSON requests
            }
        }
        return records;
    }

    /**
     * Enqueue many mock responses so the plugin never blocks on a missing response.
     */
    private void enqueueResponses(int count) {
        for (int i = 0; i < count; i++) {
            mockServer.enqueue(new MockResponse().setResponseCode(200).setBody("{\"status\":\"ok\"}"));
        }
    }

    @Test
    public void testParametersInOutput() throws Exception {
        enqueueResponses(100);

        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-params");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: '" + mockUrl + "', pipeline: true, " +
            "application: 'myapp', component: 'builder', " +
            "area: 'ci', environment: 'staging', version: '1.2.3') {\n" +
            "  echo 'param test line'\n" +
            "}\n",
            true
        ));

        jenkins.buildAndAssertSuccess(job);

        List<JsonObject> records = collectRecords();
        assertFalse("Should have received records", records.isEmpty());

        // Find non-lifecycle records (those without area=jenkins-plugin)
        List<JsonObject> logRecords = new ArrayList<>();
        for (JsonObject rec : records) {
            if (!rec.has("area") || !"jenkins-plugin".equals(rec.get("area").getAsString())) {
                logRecords.add(rec);
            }
        }
        assertFalse("Should have non-lifecycle records", logRecords.isEmpty());

        for (JsonObject rec : logRecords) {
            assertEquals("myapp", rec.get("application").getAsString());
            assertEquals("builder", rec.get("component").getAsString());
            assertEquals("ci", rec.get("area").getAsString());
            assertEquals("staging", rec.get("environment").getAsString());
            assertEquals("1.2.3", rec.get("version").getAsString());
        }

        // Also check that all records have the right application/component
        for (JsonObject rec : records) {
            assertEquals("myapp", rec.get("application").getAsString());
            assertEquals("builder", rec.get("component").getAsString());
        }
    }

    @Test
    public void testStartEndTraces() throws Exception {
        enqueueResponses(100);

        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-traces");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: '" + mockUrl + "', pipeline: true, application: 'traceapp') {\n" +
            "  echo 'trace test'\n" +
            "}\n",
            true
        ));

        jenkins.buildAndAssertSuccess(job);

        List<JsonObject> records = collectRecords();
        assertFalse("Should have received records", records.isEmpty());

        // Find records with area == "jenkins-plugin"
        List<JsonObject> events = new ArrayList<>();
        for (JsonObject rec : records) {
            if (rec.has("area") && "jenkins-plugin".equals(rec.get("area").getAsString())) {
                events.add(rec);
            }
        }

        boolean hasStarted = false;
        boolean hasCompleted = false;
        for (JsonObject evt : events) {
            String msg = evt.get("message").getAsString();
            if ("Build started".equals(msg)) hasStarted = true;
            if ("Build completed".equals(msg)) hasCompleted = true;
        }

        assertTrue("Should have 'Build started' event", hasStarted);
        assertTrue("Should have 'Build completed' event", hasCompleted);
    }

    @Test
    public void testOperationIdConsistency() throws Exception {
        enqueueResponses(100);

        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-opid");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: '" + mockUrl + "', pipeline: true, application: 'opidapp') {\n" +
            "  echo 'line one'\n" +
            "  echo 'line two'\n" +
            "  echo 'line three'\n" +
            "}\n",
            true
        ));

        jenkins.buildAndAssertSuccess(job);

        List<JsonObject> records = collectRecords();
        assertFalse("Should have received records", records.isEmpty());

        // All records should have the same non-null operation_id
        String firstOpId = null;
        for (JsonObject rec : records) {
            assertTrue("Record should have operation_id", rec.has("operation_id"));
            String opId = rec.get("operation_id").getAsString();
            assertNotNull("operation_id should not be null", opId);
            assertFalse("operation_id should not be empty", opId.isEmpty());
            if (firstOpId == null) {
                firstOpId = opId;
            } else {
                assertEquals("All records should have the same operation_id", firstOpId, opId);
            }
        }
    }

    @Test
    public void testLevelDetection() throws Exception {
        enqueueResponses(100);

        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-levels");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: '" + mockUrl + "', pipeline: true, application: 'levelapp') {\n" +
            "  echo 'ERROR: something broke'\n" +
            "  echo 'WARNING: be careful'\n" +
            "  echo 'just a normal line'\n" +
            "}\n",
            true
        ));

        jenkins.buildAndAssertSuccess(job);

        List<JsonObject> records = collectRecords();
        assertFalse("Should have received records", records.isEmpty());

        boolean hasError = false;
        boolean hasWarning = false;
        boolean hasInfo = false;

        for (JsonObject rec : records) {
            String msg = rec.get("message").getAsString();
            String level = rec.get("level").getAsString();

            if (msg.contains("ERROR: something broke")) {
                assertEquals("error", level);
                hasError = true;
            }
            if (msg.contains("WARNING: be careful")) {
                assertEquals("warning", level);
                hasWarning = true;
            }
            if (msg.contains("just a normal line")) {
                assertEquals("info", level);
                hasInfo = true;
            }
        }

        assertTrue("Should have found error-level record", hasError);
        assertTrue("Should have found warning-level record", hasWarning);
        assertTrue("Should have found info-level record", hasInfo);
    }
}
