package io.github.dandriscoll.devlogs;

import hudson.model.Result;
import org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition;
import org.jenkinsci.plugins.workflow.job.WorkflowJob;
import org.jenkinsci.plugins.workflow.job.WorkflowRun;
import org.junit.Rule;
import org.junit.Test;
import org.jvnet.hudson.test.JenkinsRule;

import static org.junit.Assert.*;

/**
 * Tests for the Devlogs Jenkins plugin.
 */
public class DevlogsStepTest {
    
    @Rule
    public JenkinsRule jenkins = new JenkinsRule();
    
    @Test
    public void testDevlogsStepWithNoUrl() throws Exception {
        // Test that the step works as a pass-through when no URL is provided
        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-no-url");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: '') {\n" +
            "  echo 'Hello World'\n" +
            "}\n",
            true
        ));
        
        WorkflowRun run = jenkins.buildAndAssertSuccess(job);
        jenkins.assertLogContains("Hello World", run);
    }
    
    @Test
    public void testDevlogsStepWithUrl() throws Exception {
        // Test that the step doesn't fail when a URL is provided
        // Note: This won't actually send logs since we don't have a real OpenSearch instance
        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-with-url");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: 'https://admin:pass@localhost:9200/test-index') {\n" +
            "  echo 'Building project'\n" +
            "  echo 'Build complete'\n" +
            "}\n",
            true
        ));
        
        WorkflowRun run = jenkins.buildAndAssertSuccess(job);
        jenkins.assertLogContains("Building project", run);
        jenkins.assertLogContains("Build complete", run);
    }
    
    @Test
    public void testDevlogsStepWithFailingBuild() throws Exception {
        // Test that the step properly handles build failures
        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-failure");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: '') {\n" +
            "  error('Build failed intentionally')\n" +
            "}\n",
            true
        ));
        
        WorkflowRun run = jenkins.assertBuildStatus(Result.FAILURE, job.scheduleBuild2(0));
        jenkins.assertLogContains("Build failed intentionally", run);
    }
    
    @Test
    public void testDevlogsStepDescriptor() {
        DevlogsStep.DescriptorImpl descriptor = new DevlogsStep.DescriptorImpl();
        
        assertEquals("devlogs", descriptor.getFunctionName());
        assertEquals("Stream logs to Devlogs", descriptor.getDisplayName());
        assertTrue(descriptor.takesImplicitBlockArgument());
    }
    
    @Test
    public void testDevlogsStepGetters() {
        DevlogsStep step = new DevlogsStep();
        step.setUrl("https://example.com:9200/test");

        assertEquals("https://example.com:9200/test", step.getUrl());
        assertNull(step.getIndex());
        assertNull(step.getCredentialsId());

        step.setIndex("custom-index");
        assertEquals("custom-index", step.getIndex());

        step.setCredentialsId("my-creds");
        assertEquals("my-creds", step.getCredentialsId());
    }

    @Test
    public void testOpenSearchUrlAutoDetection() throws Exception {
        // OpenSearch URL (user:password) should be detected and show OpenSearch mode
        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-opensearch-url");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: 'https://admin:password@opensearch.example.com:9200/myindex') {\n" +
            "  echo 'Test'\n" +
            "}\n",
            true
        ));

        WorkflowRun run = jenkins.buildAndAssertSuccess(job);
        jenkins.assertLogContains("Streaming logs directly to OpenSearch index 'myindex'", run);
    }

    @Test
    public void testCollectorUrlAutoDetection() throws Exception {
        // Collector URL (token only, no password) should be detected as collector mode
        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-collector-url");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: 'https://dl1_mytoken@collector.example.com') {\n" +
            "  echo 'Test'\n" +
            "}\n",
            true
        ));

        WorkflowRun run = jenkins.buildAndAssertSuccess(job);
        jenkins.assertLogContains("Streaming logs to collector", run);
    }

    @Test
    public void testPlainUrlDefaultsToCollector() throws Exception {
        // URL without credentials should default to collector mode
        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-plain-url");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: 'https://collector.example.com') {\n" +
            "  echo 'Test'\n" +
            "}\n",
            true
        ));

        WorkflowRun run = jenkins.buildAndAssertSuccess(job);
        jenkins.assertLogContains("Streaming logs to collector", run);
    }

    @Test
    public void testPipelineParameterOverridesAutoDetection() throws Exception {
        // Explicit pipeline: false should override auto-detection
        WorkflowJob job = jenkins.createProject(WorkflowJob.class, "test-pipeline-override");
        job.setDefinition(new CpsFlowDefinition(
            "devlogs(url: 'https://token@example.com', pipeline: false) {\n" +
            "  echo 'Test'\n" +
            "}\n",
            true
        ));

        WorkflowRun run = jenkins.buildAndAssertSuccess(job);
        jenkins.assertLogContains("Streaming logs directly to OpenSearch", run);
    }

    @Test
    public void testPipelineNullAllowsAutoDetection() {
        // When pipeline is null, auto-detection should be used
        DevlogsStep step = new DevlogsStep();
        assertNull(step.getPipeline());

        step.setPipeline(true);
        assertEquals(Boolean.TRUE, step.getPipeline());

        step.setPipeline(false);
        assertEquals(Boolean.FALSE, step.getPipeline());

        step.setPipeline(null);
        assertNull(step.getPipeline());
    }
}
