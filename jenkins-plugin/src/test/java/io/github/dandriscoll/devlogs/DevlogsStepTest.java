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
        DevlogsStep step = new DevlogsStep("https://example.com:9200/test");
        
        assertEquals("https://example.com:9200/test", step.getUrl());
        assertNull(step.getIndex());
        
        step.setIndex("custom-index");
        assertEquals("custom-index", step.getIndex());
    }
}
